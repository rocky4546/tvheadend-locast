# Licensed under the MIT license
# http://opensource.org/licenses/mit-license.php
#

import logging
import random
import time
import socket
import struct
import zlib
import sched
import requests
from multiprocessing import Process, Queue
from urllib.parse import urlparse
from threading import Thread
from email.utils import formatdate
from errno import ENOPROTOOPT
from queue import Empty
from ipaddress import IPv4Network
from ipaddress import IPv4Address

import lib.tvheadend.utils as utils

HDHR_PORT = 65001
HDHR_ADDR = '224.0.0.255'           # multicast to local addresses only
SERVER_ID = 'HDHR3'
HDHOMERUN_TYPE_DISCOVER_REQ = 2
HDHOMERUN_TYPE_DISCOVER_RSP = 3
HDHOMERUN_TYPE_GETSET_REQ = 4
HDHOMERUN_TYPE_GETSET_RSP = 5
HDHOMERUN_GETSET_NAME = 3
HDHOMERUN_GETSET_VALUE = 4
HDHOMERUN_ERROR_MESSAGE = 5
HDHOMERUN_GETSET_LOCKKEY = 21
START_SEND_UDP_ATSC_PKTS = 1
STOP_SEND_UDP_ATSC_PKTS = 0

msgs = {
    'lockedErrMsg':
        """ERROR: resource locked by {}""",
    }

def hdhr_process(config):
    pqueue = Queue()
    hdhr = HDHRServer(config)
    
    # startup the multicast thread first which will exit when this function exits
    p_multi = Process(target=hdhr.run_multicast, args=(pqueue,config["main"]["bind_ip"],))
    p_multi.daemon = True
    p_multi.start()
    
    # startup the standard tcp listener, but have this hang the process
    # the socket listener will terminate from main.py when the process is stopped
    hdhr.run_listener(pqueue,config["main"]["bind_ip"])
    logging.info('hdhr_processing terminated')

class HDHRServer:
    """A class implementing a HDHR server.  The notify_received and
    searchReceived methods are called when the appropriate type of
    datagram is received by the server."""
    known = {}
    

    def __init__(self, _config):
        self.config = _config
        self.sock_multicast = None
        self.sock_listener =  None
        self.queue = None
        self.tuners = dict.fromkeys(range(self.config["main"]["tuner_count"]))
        for i in range(3):
            self.tuners[i] = {'lockkey':b'none', 'ch':None, 'target':b'none', \
                'filter':b'0x0000', 'pps':None, 'bps':None, 'status':'idle', \
                'chnum':None, 'mux':None }

    def run_listener(self, _queue, bindIP=''):
        self.queue = _queue
        logging.info('TCP: Starting HDHR TCP listener server')
        self.sock_listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_address = (bindIP, HDHR_PORT)
        self.sock_listener.bind(server_address)
        self.sock_listener.listen(3)
        
        while True:
            # wait for a connection
            connection, client_address = self.sock_listener.accept()
            t_conn = Thread(target=self.process_client_connection, args=(connection, client_address,))
            t_conn.daemon = True
            t_conn.start()


    def process_client_connection(self, connection, address):
        # multi-threading multiple clients talking to the device at one time
        # buffer must be large enough to hold a full rcvd packets
        logging.debug('TCP: New connection established {}'.format(address))
        try:
            while True:
                msg = connection.recv(500)
                if not msg:
                    # client disconnect
                    logging.debug('TCP: Client terminated connection {}'.format(address))
                    break
                logging.debug('TCP: data rcvd={}'.format(msg))
                frame_type = self.get_frame_type(msg)
                if frame_type == HDHOMERUN_TYPE_GETSET_REQ:
                    req_dict = self.parse_getset_request(msg)
                    response = self.create_getset_response(req_dict, address)
                    if response is not None:
                        logging.debug('TCP: Sending response={}'.format(response))
                        connection.sendall(response)
                else:
                    logging.error('TCP: Unknown frame/message type from {} type={}'.format(address, frame_type))
        finally:
            connection.close()


    # get the type of message requested        
    def get_frame_type(self, msg):
        # msg is in the first 2 bytes of the string
        (frame_type,) = struct.unpack('>H', msg[:2])
        return frame_type


    def gen_err_response(self, frame_type, tag, input):
        # This is a tag type of HDHOMERUN_ERROR_MESSAGE
        # does not include the crc
        msg = msgs[tag].format(*input).encode()
        tag = utils.set_u8(HDHOMERUN_ERROR_MESSAGE)
        err_resp = utils.set_str(msg ,True)
        msg_len = utils.set_u16(len(tag)+len(err_resp))
        response = frame_type + msg_len + tag + err_resp
        return response
        
    def create_getset_response(self, req_dict, address):
        (host, port) = address
        frame_type = utils.set_u16(HDHOMERUN_TYPE_GETSET_RSP)
        name = req_dict[HDHOMERUN_GETSET_NAME]
        name_str = name.decode('utf-8')
        if HDHOMERUN_GETSET_VALUE in req_dict.keys():
            value = req_dict[HDHOMERUN_GETSET_VALUE]
        else:
            value = None

        if name == b'/sys/model':
            # required to id the device
            name_resp = utils.set_u8(HDHOMERUN_GETSET_NAME) + utils.set_str(name, True)
            value_resp = utils.set_u8(HDHOMERUN_GETSET_VALUE) + utils.set_str(b'hdhomerun4_atsc', True)
            msg_len = utils.set_u16(len(name_resp) + len(value_resp))
            response = frame_type + msg_len + name_resp + value_resp
            x = zlib.crc32(response)
            crc = struct.pack('<I', x)
            response += crc
            return response
        
        elif name_str.startswith('/tuner'):
            tuner_index = int(name_str[6])
            if name_str.endswith('/lockkey'):
                logging.error('TCP: NOT IMPLEMENTED GETSET LOCKKEY MSG REQUEST: {} '.format(req_dict))
                response = self.gen_err_response(frame_type, 'lockedErrMsg', [host])
                x = zlib.crc32(response)
                crc = struct.pack('<I', x)
                response += crc
                return response
            else:
                logging.error('TCP: NOT IMPLEMENTED GETSET MSG REQUEST: {} '.format(req_dict))
                return None
        else:
            logging.error('TCP: 3 UNKNOWN GETSET MSG REQUEST: {} '.format(req_dict))
            return None


    def parse_getset_request(self, msg):
        (crc_rcvd,) = struct.unpack('I', msg[-4:])
        crc_calc = zlib.crc32(msg[0:-4])
        if crc_calc == crc_rcvd:
            #Pull first id/value
            offset = 4
            request_info = {}
            while True:
                (type, value, offset) = self.get_id_value(msg, offset)
                if type is None:
                    break
                request_info[type] = value
        else:
            logging.info('TCP: type/value CRC failed, ignoring packet')
            return None
        
        return request_info


    # obtains the next type/value in the message and moves the offset to the next spot
    def get_id_value(self, msg, offset):
        if offset >= len(msg)-4:
            return (None, None, None)
        (type,length) = struct.unpack('BB', msg[offset:offset+2])
        offset += 2
        (value,) = struct.unpack('%ds' % (length-1), msg[offset:offset+length-1])
        offset += length
        return (type, value, offset)



    def run_multicast(self, _queue, bindIP=''):
        logging.info('UDP: Starting HDHR multicast server')
        self.queue = _queue
        self.send_msg_events = sched.scheduler(time.time, time.sleep)
        
        self.sock_multicast = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.sock_multicast.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, "SO_REUSEPORT"):
            try:
                self.sock_multicast.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except socket.error as le:
                # RHEL6 defines SO_REUSEPORT but it doesn't work
                if le.errno == ENOPROTOOPT:
                    pass
                else:
                    raise

        self.sock_multicast.bind((bindIP, HDHR_PORT))
        mreq = struct.pack('4sl', socket.inet_aton(HDHR_ADDR), socket.INADDR_ANY)
        self.sock_multicast.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        self.sock_multicast.settimeout(2)

        while True:
            try:
                data, addr = self.sock_multicast.recvfrom(1024)
                self.datagram_received(data, addr)
            except socket.timeout:
                continue


    def datagram_received(self, data, host_port):
        """Handle a received multicast datagram."""

        (host, port) = host_port
        if self.config['hdhomerun']['udp_netmask'] is None:
            isAllowed = True
        else:
            net = IPv4Network(self.config['hdhomerun']['udp_netmask'])
            isAllowed = IPv4Address(host) in net

        if isAllowed:
            logging.debug('UDP: from {}:{}'.format(host, port))
            try:
                (frame_type, msg_len, device_type, sub_dt_len, sub_dt, device_id, sub_did_len, sub_did) = \
                    struct.unpack('>HHBBIBBI', data[0:-4])
                (crc,) = struct.unpack('<I', data[-4:])
            except ValueError as err:
                logging.error('UDP: {}'.format(err))
                return

            if frame_type != HDHOMERUN_TYPE_DISCOVER_REQ:
                logging.error('UDP: Unknown from type = {}'.format(frame_type))
            else:
                msg_type = bytes.fromhex('0003')
                header = bytes.fromhex('010400000001')
                if self.config['hdhomerun']['hdhr_id'] is None:
                    device_id = '0'
                device_id = bytes.fromhex('0204'+self.config['hdhomerun']['hdhr_id'])
                base_url = 'http://' + \
                    self.config['main']['plex_accessible_ip'] + \
                    ':' + self.config['main']['plex_accessible_port']
                base_url = utils.set_str(base_url.encode(),False)
                base_url_msg = b'\x2a'+utils.set_u8(len(base_url))+base_url
                tuner_count = b'\x10\x01' + utils.set_u8(self.config['main']['tuner_count'])

                lineup_url = base_url + b'/lineup.json'
                lineup_url = b'\x27' + utils.set_u8(len(lineup_url)) + lineup_url
                msg = header + device_id + base_url_msg + tuner_count + lineup_url
                msg_len = utils.set_u16(len(msg))
                response = msg_type + msg_len + msg
                
                x = zlib.crc32(response)
                crc = struct.pack('<I', x)
                response += crc
                logging.debug('UDP Response={} {}'.format(host_port, response))
                self.sock_multicast.sendto(response, host_port)
