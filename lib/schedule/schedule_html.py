"""
MIT License

Copyright (C) 2021 ROCKY4546
https://github.com/rocky4546

This file is part of Cabernet

Permission is hereby granted, free of charge, to any person obtaining a copy of this software
and associated documentation files (the "Software"), to deal in the Software without restriction,
including without limitation the rights to use, copy, modify, merge, publish, distribute,
sublicense, and/or sell copies of the Software, and to permit persons to whom the Software
is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or
substantial portions of the Software.
"""

import datetime
import json
import logging
import time

from lib.common.decorators import getrequest
from lib.common.decorators import postrequest
from lib.db.db_scheduler import DBScheduler


@getrequest.route('/pages/schedule.html')
def get_schedule_html(_webserver):
    schedule_html = ScheduleHTML(_webserver.config, _webserver.sched_queue)
    if 'run' in _webserver.query_data:
        schedule_html.run_task(_webserver.query_data['task'])
        time.sleep(0.51)
        html = schedule_html.get()
    elif 'delete' in _webserver.query_data:
        schedule_html.del_trigger(_webserver.query_data['trigger'])
        time.sleep(0.51)
        html = schedule_html.get_task(_webserver.query_data['task'])
    elif 'trigger' in _webserver.query_data:
        html = schedule_html.get_trigger(_webserver.query_data['task'])
    elif 'task' in _webserver.query_data:
        html = schedule_html.get_task(_webserver.query_data['task'])
    else:
        html = schedule_html.get()
    _webserver.do_mime_response(200, 'text/html', html)


@postrequest.route('/pages/schedule.html')
def post_schedule_html(_webserver):
    schedule_html = ScheduleHTML(_webserver.config, _webserver.sched_queue)
    html = schedule_html.post_add_trigger(_webserver.query_data)
    _webserver.do_mime_response(200, 'text/html', html)


class ScheduleHTML:

    def __init__(self, _config, _queue):
        self.logger = logging.getLogger(__name__)
        self.config = _config
        self.queue = _queue
        self.scheduler_db = DBScheduler(self.config)

    def get(self):
        return ''.join([self.header, self.body])

    @property
    def header(self):
        return ''.join([
            '<!DOCTYPE html><html><head>',
            '<meta charset="utf-8"/><meta name="author" content="rocky4546">',
            '<meta name="description" content="database management for Cabernet">',
            '<title>Scheduled Tasks</title>',
            '<meta name="viewport" content="width=device-width, ',
            'minimum-scale=1.0, maximum-scale=1.0">',
            '<script src="https://code.jquery.com/jquery-3.5.1.min.js"></script>',
            '<link rel="stylesheet" type="text/css" href="/modules/scheduler/scheduler.css">',
            '<script src="/modules/scheduler/scheduler.js"></script>',
        ])

    @property
    def body(self):
        return ''.join(['<body>', self.title, self.schedule_tasks, self.task,
            '</body>'
            ])
    
    @property
    def title(self):
        return ''.join([
            '<div class="container">',
            '<h2>Scheduled Tasks</h2>'
        ])

    @property
    def schedule_tasks(self):
        tasks = self.scheduler_db.get_tasks()
        current_area = None

        html = ''.join([
            '<div id="schedtasks" class="schedShow">',
            '<table class="schedTable" width=95%>'
        ])
        for task_dict in tasks:
            if task_dict['area'] != current_area:
                current_area = task_dict['area']
                html = ''.join([html,
                    '<tr>',
                    '<td colspan=3><div class="schedSection">',
                    current_area, '</div></td>'
                    '</tr>',
                ])

            lastran_delta = datetime.datetime.utcnow() - task_dict['lastran']
            lastran_secs = int(lastran_delta.total_seconds())
            lastran_mins = lastran_secs // 60
            lastran_hrs = lastran_mins // 60
            lastran_days = lastran_hrs // 24
            if lastran_days != 0:
                lastran_delta = str(lastran_days) + ' days'
            elif lastran_hrs != 0:
                lastran_delta = str(lastran_hrs) + ' hours'
            elif lastran_mins != 0:
                lastran_delta = str(lastran_mins) + ' minutes'
            else:
                lastran_delta = str(lastran_secs) + ' seconds'

            dur_mins = task_dict['duration'] // 60
            dur_hrs = dur_mins // 60
            dur_days = dur_hrs // 24
            if dur_days != 0:
                dur_delta = str(dur_days) + ' days'
            elif dur_hrs != 0:
                dur_delta = str(dur_hrs) + ' hours'
            elif dur_mins != 0:
                dur_delta = str(dur_mins) + ' minutes'
            else:
                dur_delta = str(task_dict['duration']) + ' seconds'

            html = ''.join([html,
                '<tr>',
                '<td class="schedIcon">',
                '<a href="#" onclick=\'load_task_url("/pages/schedule.html?task=', 
                task_dict['taskid'], '")\'>',
                '<i class="md-icon">schedule</i></a></td>',
                '<td class="schedTask">',
                '<a href="#" onclick=\'load_task_url("/pages/schedule.html?task=',
                task_dict['taskid'], '")\'>',
                '<div class="schedTitle">', task_dict['title'], '</div>',
                '<div>Last ran ', lastran_delta, ' ago, ',
                'taking ', dur_delta, '</div>'
            ])

            if task_dict['active']:
                html = ''.join([html,
                    '<div class="progress-line"></div>'
                ])
                play_name = ''
                play_icon = ''
            else:
                html = ''.join([html,
                    '<div class=""></div>'
                ])
                play_name = '&run=1'
                play_icon = 'play_arrow'

            html = ''.join([html,
                '</a></td>',
                '<td class="schedIcon">',
                '<a href="#" onclick=\'load_sched_url("/pages/schedule.html?task=',
                task_dict['taskid'], play_name, '")\'>',
                '<i class="md-icon">', play_icon, '</i></a></td>',
                '</tr>',
                '<tr>',
                '<td colspan=3><hr></td>',
                '</tr>'
            ])
        return ''.join([html, '</table></div>'])
 
    @property 
    def task(self):
        return ''.join([
            '<div id="schedtask" class="schedTable schedHide"></div>'
        ])

    def get_task(self, _id):
        task_dict = self.scheduler_db.get_task(_id)
        if task_dict is None:
            self.logger.warning('Invalid task id: {}'.format(_id))
            return ''

        self.queue.put({'cmd': 'prep'})

        html = ''.join([
            '<table style="display: contents" width=95%>',
            '<tr>',
            '<td class="schedIcon">',
            '<a href="#" onclick=\'display_tasks()\'>',
            '<div ><i class="md-icon">arrow_back</i></div></a>',
            '<td colspan=2 ><div class="schedSection">',
            str(task_dict['title']), '</div></td>',
            '</tr>',
            '<tr>',
            '<td class="schedIcon"></td>',
            '<td colspan=2>', str(task_dict['description']), '</div></td>'
            '</tr>',
            '<td class="schedIcon"></td>',
            '<td colspan=2><b>Namespace:</b> ', str(task_dict['namespace']), 
            ' &nbsp; <b>Instance:</b> ', str(task_dict['instance']),
            ' &nbsp; <b>Priority:</b> ', str(task_dict['priority']), 
            ' &nbsp; <b>Thread Type:</b> ', str(task_dict['threadtype']), 
            '</div></td>',
            '<tr>',
            '<tr><td>&nbsp;</td></tr>',
            '<td colspan=3><div class="schedSection">Task Triggers',
            '<button class="schedIconButton" onclick=\'load_task_url(',
            '"/pages/schedule.html?task=', _id, '&trigger=1");return false;\'>',
            '<i class="schedIcon md-icon" style="padding-left: 1px; text-align: left;">add</i></button>',
            '</div></td>',
            '</tr>',
            ])

        trigger_array = self.scheduler_db.get_triggers(_id)
        for trigger_dict in trigger_array:
            if trigger_dict['timetype'] == 'startup':
                trigger_str = 'At startup'
            elif trigger_dict['timetype'] == 'daily':
                trigger_str = 'Daily at ' + trigger_dict['timeofday']
            elif trigger_dict['timetype'] == 'weekly':
                trigger_str = ''.join([
                    'Every ', trigger_dict['dayofweek'],
                    ' at ', trigger_dict['timeofday']
                    ])
            elif trigger_dict['timetype'] == 'interval':
                interval_mins = trigger_dict['interval']
                remainder_hrs = interval_mins % 60
                if remainder_hrs != 0:
                    interval_str = str(interval_mins) + ' minutes'
                else:
                    interval_hrs = interval_mins // 60
                    interval_str = str(interval_hrs) + ' hours'
                trigger_str = 'Every ' + interval_str
                if trigger_dict['randdur'] != -1:
                    trigger_str += ' with random maximum added time of ' + str(trigger_dict['randdur']) + ' minutes'
                
            else:
                trigger_str = 'UNKNOWN'
        
            html = ''.join([
                html,
                '<tr>',
                '<td class="schedIcon">',
                '<i class="md-icon">schedule</i></td>',
                '<td class="schedTask">',
                trigger_str,
                '</td>',
                '<td class="schedIcon">',
                '<a href="#" onclick=\'load_task_url("/pages/schedule.html?task=', _id, 
                '&trigger=', trigger_dict['uuid'], '&delete=1")\'>',
                '<i class="md-icon">delete_forever</i></a></td>',
                '</tr>'
                ])

        return ''.join([
            html,
            '</table>'
            ])

    def get_trigger(self, _id):
        task_dict = self.scheduler_db.get_task(_id)
        if task_dict is None:
            self.logger.warning('Invalid task id: {}'.format(_id))
            return ''
        if task_dict['namespace'] is None:
            namespace = ""
        else:
            namespace = task_dict['namespace']
        if task_dict['instance'] is None:
            instance = ""
        else:
            instance = task_dict['instance']
            
        return "".join([
            '<script src="/modules/scheduler/trigger.js"></script>',
            '<form id="triggerform" action="/pages/schedule.html" method="post">',
            '<input type="hidden" name="name" value="', namespace, '" >',
            '<input type="hidden" name="instance" value="', instance, '" >',
            '<input type="hidden" name="area" value="', task_dict['area'], '" >',
            '<table style="display: contents" width=95%>',
            '<tr>',
            '<td style="display: flex;">',
            '<a href="#" onclick=\'load_task_url("/pages/schedule.html?task=', _id, '");\'>',
            '<div ><i class="schedIcon md-icon">arrow_back</i></div></a>',
            '<div class="schedSection">',
            'Add Trigger</div></td>'
            '</tr>',
            '<tr>',
            '<td><b>Task: ', task_dict['title'], 
            '<input type="hidden" name="title" value="', task_dict['title'], '" >',
            '</b><br><br></td>'
            '</tr>',
            '<tr><td>Trigger Type: &nbsp; ',
            '<select id="timetype" name="timetype"</select>',
            '<option value="daily">Daily</option>',
            '<option value="weekly">Weekly</option>',
            '<option value="interval">On an interval</option>',
            '<option value="startup">On Startup</option>',
            '</select><br><br>',
            '<script>',
            '$("#timetype").change(function(){ onChangeTimeType( this ); });',
            '</script>',
            '</td></tr>',
            '<tr><td><div id="divDOW" class="schedHide">Day: &nbsp; ',
            '<select name="dayofweek"</select>',
            '<option value="">Not Set</option>',
            '<option value="Sunday">Sunday</option>',
            '<option value="Monday">Monday</option>',
            '<option value="Tuesday">Tuesday</option>',
            '<option value="Wednesday">Wednesday</option>',
            '<option value="Thursday">Thursday</option>',
            '<option value="Friday">Friday</option>',
            '<option value="Saturday">Saturday</option>',
            '</select>',
            '<br><br>',
            '</div></td></tr>',
            '<tr><td><div id="divTOD" class="schedShow">Time: &nbsp; ',
            '<select name="timeofday"</select>',
            '<option value="">Not set</option>',
            '<option value="12:00">12:00 AM</option>',
            '<option value="12:15">12:15 AM</option>',
            '<option value="12:30">12:30 AM</option>',
            '<option value="12:45">12:45 AM</option>',
            '<option value="01:00">1:00 AM</option>',
            '<option value="01:15">1:15 AM</option>',
            '<option value="01:30">1:30 AM</option>',
            '<option value="01:45">1:45 AM</option>',
            '<option value="02:00">2:00 AM</option>',
            '<option value="02:15">2:15 AM</option>',
            '<option value="02:30">2:30 AM</option>',
            '<option value="02:45">2:45 AM</option>',
            '<option value="03:00">3:00 AM</option>',
            '<option value="03:15">3:15 AM</option>',
            '<option value="03:30">3:30 AM</option>',
            '<option value="03:45">3:45 AM</option>',
            '<option value="04:00">4:00 AM</option>',
            '<option value="04:15">4:15 AM</option>',
            '<option value="04:30">4:30 AM</option>',
            '<option value="04:45">4:45 AM</option>',
            '<option value="05:00">5:00 AM</option>',
            '<option value="05:15">5:15 AM</option>',
            '<option value="05:30">5:30 AM</option>',
            '<option value="05:45">5:45 AM</option>',
            '<option value="06:00">6:00 AM</option>',
            '<option value="06:15">6:15 AM</option>',
            '<option value="06:30">6:30 AM</option>',
            '<option value="06:45">6:45 AM</option>',
            '<option value="07:00">7:00 AM</option>',
            '<option value="07:15">7:15 AM</option>',
            '<option value="07:30">7:30 AM</option>',
            '<option value="07:45">7:45 AM</option>',
            '<option value="08:00">8:00 AM</option>',
            '<option value="08:15">8:15 AM</option>',
            '<option value="08:30">8:30 AM</option>',
            '<option value="08:45">8:45 AM</option>',
            '<option value="09:00">9:00 AM</option>',
            '<option value="09:15">9:15 AM</option>',
            '<option value="09:30">9:30 AM</option>',
            '<option value="09:45">9:45 AM</option>',
            '<option value="10:00">10:00 AM</option>',
            '<option value="10:15">10:15 AM</option>',
            '<option value="10:30">10:30 AM</option>',
            '<option value="10:45">10:45 AM</option>',
            '<option value="11:00">11:00 AM</option>',
            '<option value="11:15">11:15 AM</option>',
            '<option value="11:30">11:30 AM</option>',
            '<option value="11:45">11:45 AM</option>',
            '<option value="12:00">12:00 PM</option>',
            '<option value="12:15">12:15 PM</option>',
            '<option value="12:30">12:30 PM</option>',
            '<option value="12:45">12:45 PM</option>',
            '<option value="13:00">1:00 PM</option>',
            '<option value="13:15">1:15 PM</option>',
            '<option value="13:30">1:30 PM</option>',
            '<option value="13:45">1:45 PM</option>',
            '<option value="14:00">2:00 PM</option>',
            '<option value="14:15">2:15 PM</option>',
            '<option value="14:30">2:30 PM</option>',
            '<option value="14:45">2:45 PM</option>',
            '<option value="15:00">3:00 PM</option>',
            '<option value="15:15">3:15 PM</option>',
            '<option value="15:30">3:30 PM</option>',
            '<option value="15:45">3:45 PM</option>',
            '<option value="16:00">4:00 PM</option>',
            '<option value="16:15">4:15 PM</option>',
            '<option value="16:30">4:30 PM</option>',
            '<option value="16:45">4:45 PM</option>',
            '<option value="17:00">5:00 PM</option>',
            '<option value="17:15">5:15 PM</option>',
            '<option value="17:30">5:30 PM</option>',
            '<option value="17:45">5:45 PM</option>',
            '<option value="18:00">6:00 PM</option>',
            '<option value="18:15">6:15 PM</option>',
            '<option value="18:30">6:30 PM</option>',
            '<option value="18:45">6:45 PM</option>',
            '<option value="19:00">7:00 PM</option>',
            '<option value="19:15">7:15 PM</option>',
            '<option value="19:30">7:30 PM</option>',
            '<option value="19:45">7:45 PM</option>',
            '<option value="20:00">8:00 PM</option>',
            '<option value="20:15">8:15 PM</option>',
            '<option value="20:30">8:30 PM</option>',
            '<option value="20:45">8:45 PM</option>',
            '<option value="21:00">9:00 PM</option>',
            '<option value="21:15">9:15 PM</option>',
            '<option value="21:30">9:30 PM</option>',
            '<option value="21:45">9:45 PM</option>',
            '<option value="22:00">10:00 PM</option>',
            '<option value="22:15">10:15 PM</option>',
            '<option value="22:30">10:30 PM</option>',
            '<option value="22:45">10:45 PM</option>',
            '<option value="23:00">11:00 PM</option>',
            '<option value="23:15">11:15 PM</option>',
            '<option value="23:30">11:30 PM</option>',
            '<option value="23:45">11:45 PM</option>',
            '</select><br><br>',
            '</td></tr>',
            '<tr><td><div id="divINTL" class="schedHide">Every: &nbsp; ',
            '<select name="interval"</select>',
            '<option value="">Not Set</option>',
            '<option value="15">15 minutes</option>',
            '<option value="30">30 minutes</option>',
            '<option value="45">45 minutes</option>',
            '<option value="60">1 hour</option>',
            '<option value="120">2 hours</option>',
            '<option value="180">3 hours</option>',
            '<option value="240">4 hours</option>',
            '<option value="355">5 hours, 55 minutes</option>',
            '<option value="360">6 hours</option>',
            '<option value="480">8 hours</option>',
            '<option value="710">11 hours, 50 minutes</option>',
            '<option value="720">12 hours</option>',
            '<option value="1440">24 hours</option>',
            '</select><br><br>',
            '</td></tr>',
            '<tr><td><div id="divRND" class="schedHide">Max Random Added Time: &nbsp; ',
            '<select name="randdur"</select>',
            '<option value="-1">Not set</option>',
            '<option value="5">5 min</option>',
            '<option value="10">10 min</option>',
            '<option value="15">15 min</option>',
            '<option value="20">20 min</option>',
            '<option value="30">30 min</option>',
            '<option value="60">1 hour</option>',
            '<option value="120">2 hours</option>'
            '</select><br><br>',
            '</td></tr>',
            '<tr><td><button type="submit">Add</button>',
            ' &nbsp; <button onclick=\'load_task_url("/pages/schedule.html?task=', _id, '"); return false;\' >Cancel</button>',
            '<tr><td>&nbsp;</td></tr>',
            '</table></form>',
            '<section id="status"></section>'

        ])

    def post_add_trigger(self, query_data):
        if query_data['timetype'][0] == 'startup':
            self.queue.put({'cmd': 'add', 'trigger': {
                'area': query_data['area'][0],
                'title': query_data['title'][0],
                'timetype': query_data['timetype'][0]
            }})
            time.sleep(0.1)
            return 'Startup Trigger added'

        elif query_data['timetype'][0] == 'daily':
            if query_data['timeofday'][0] is None:
                return 'Time of Day is not set and is required'
            self.queue.put({'cmd': 'add', 'trigger': {
                'area': query_data['area'][0],
                'title': query_data['title'][0],
                'timetype': query_data['timetype'][0],
                'timeofday': query_data['timeofday'][0]
            }})
            time.sleep(0.1)
            return 'Daily Trigger added'

        elif query_data['timetype'][0] == 'weekly':
            if query_data['dayofweek'][0] is None:
                return 'Day of Week is not set and is required'
            elif query_data['timeofday'][0] is None:
                return 'Time of Day is not set and is required'
            self.queue.put({'cmd': 'add', 'trigger': {
                'area': query_data['area'][0],
                'title': query_data['title'][0],
                'timetype': query_data['timetype'][0],
                'timeofday': query_data['timeofday'][0],
                'dayofweek': query_data['dayofweek'][0]
            }})
            time.sleep(0.1)
            return 'Weekly Trigger added'

        elif query_data['timetype'][0] == 'interval':
            if query_data['interval'][0] is None:
                return 'Interval is not set and is required'
            self.queue.put({'cmd': 'add', 'trigger': {
                'area': query_data['area'][0],
                'title': query_data['title'][0],
                'timetype': query_data['timetype'][0],
                'interval': query_data['interval'][0],
                'randdur': query_data['randdur'][0]
            }})
            time.sleep(0.1)
            return 'Interval Trigger added'
        return 'UNKNOWN'
        
    def del_trigger(self, _uuid):
        if self.scheduler_db.get_trigger(_uuid) is None:
            return None
        self.queue.put({'cmd': 'del', 'uuid': _uuid })
        time.sleep(0.1)
        return 'Interval Trigger deleted'

    def run_task(self, _taskid):
        triggers = self.scheduler_db.get_triggers(_taskid)
        if len(triggers) == 0:
            return None

        is_run = False
        default_trigger = None
        for trigger in triggers:
            if trigger['timetype'] == 'startup':
                continue
            elif trigger['timetype'] == 'interval':
                self.queue.put({'cmd': 'run', 'uuid': trigger['uuid'] })
                time.sleep(0.1)
                is_run = True
                break
            else:
                default_trigger = trigger
        if not is_run and default_trigger is not None:
            self.queue.put({'cmd': 'run', 'uuid': trigger['uuid'] })
            time.sleep(0.1)
        else:
            self.logger.warning('Need at least one non-startup trigger event to run manually')
        return None

