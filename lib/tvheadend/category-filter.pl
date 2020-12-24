#!/usr/bin/perl -w
use strict;
use warnings;
use Data::Dumper;
use XML::DOM;


# KODI COLOR MAPPINGS
# 0 Other/Unknown Grey
# 16 Movie Orange
# 32 News Light Green
# 48 TV Show Yellow
# 64 Sports Red
# 80 Child Cyan
# 96 Music Green
# 112 Arts Blue
# 128 Social Light Grey
# 144 Science Purple
# 160 Hobby Light Purple
# 176 Special Light Blue
# 192 Other/Unknown Grey
# 208 Other/Unknown Grey
# 224 Other/Unknown Grey
# 240 Other/Unknown Grey



#
# The categories recognized by tvheadend (see epg.c) (last checked 12/2/2020
#  
my $MOVIE             =    "Movie / Drama";
my $THRILLER          =    "Detective / Thriller";
my $ADVENTURE         =    "Adventure / Western / War";
my $SF                =    "Science fiction / Fantasy / Horror";
my $COMEDY            =    "Comedy";
my $SOAP              =    "Soap / Melodrama / Folkloric";
my $ROMANCE           =    "Romance";
my $HISTORICAL        =    "Serious / Classical / Religious / Historical movie / Drama";
my $XXX               =    "Adult movie / Drama";

my $NEWS              =    "News / Current affairs";
my $WEATHER           =    "News / Weather report";
my $NEWS_MAGAZINE     =    "News magazine";
my $DOCUMENTARY       =    "Documentary";
my $DEBATE            =    "Discussion / Interview / Debate";
my $INTERVIEW         =    $DEBATE ;

my $SHOW              =    "Show / Game show";
my $GAME              =    "Game show / Quiz / Contest";
my $VARIETY           =    "Variety show";
my $TALKSHOW          =    "Talk show";

my $SPORT             =    "Sports";
my $SPORT_SPECIAL     =    "Special events (Olympic Games; World Cup; etc.)";
my $SPORT_MAGAZINE    =    "Sports magazines";
my $FOOTBALL          =    "Football / Soccer";
my $TENNIS            =    "Tennis / Squash";
my $SPORT_TEAM        =    "Team sports (excluding football)";
my $ATHLETICS         =    "Athletics";
my $SPORT_MOTOR       =    "Motor sport";
my $SPORT_WATER       =    "Water sport";
my $SPORT_WINTER      =    "Winter sports";
my $SPORT_HORSES      =    "Equestrian";
my $MARTIAL_ARTS      =    "Martial sports";

my $KIDS              =    "Children's / Youth programs";
my $KIDS_0_5          =    "Pre-school children's programs";
my $KIDS_6_14         =    "Entertainment programs for 6 to 14";
my $KIDS_10_16        =    "Entertainment programs for 10 to 16";
my $EDUCATIONAL       =    "Informational / Educational / School programs";
my $CARTOON           =    "Cartoons / Puppets";

my $MUSIC             =    "Music / Ballet / Dance";
my $ROCK_POP          =    "Rock / Pop";
my $CLASSICAL         =    "Serious music / Classical music";
my $FOLK              =    "Folk / Traditional music";
my $JAZZ              =    "Jazz";
my $OPERA             =    "Musical / Opera";
my $BALLET            =    "Ballet";

my $CULTURE           =    "Arts / Culture (without music)";
my $PERFORMING        =    "Performing arts";
my $FINE_ARTS         =    "Fine arts";
my $RELIGION          =    "Religion";
my $POPULAR_ART       =    "Popular culture / Traditional arts";
my $LITERATURE        =    "Literature";
my $FILM              =    "Film / Cinema";
my $EXPERIMENTAL_FILM =    "Experimental film / Video";
my $BROADCASTING      =    "Broadcasting / Press";
my $NEWMEDIA          =    "New media";
my $ARTS_MAGAZINE     =    "Arts magazines / Culture magazines";
my $FASHION           =    "Fashion";

my $SOCIAL            =    "Social / Political issues / Economics";
my $MAGAZINE          =    "Magazines / Reports / Documentary";
my $ECONOMIC          =    "Economics / Social advisory";
my $VIP               =    "Remarkable people";

my $SCIENCE           =    "Education / Science / Factual topics";
my $NATURE            =    "Nature / Animals / Environment";
my $TECHNOLOGY        =    "Technology / Natural sciences";
my $DIOLOGY           =    $TECHNOLOGY;
my $MEDICINE          =    "Medicine / Physiology / Psychology";
my $FOREIGN           =    "Foreign countries / Expeditions";
my $SPIRITUAL         =    "Social / Spiritual sciences";
my $FURTHER_EDUCATION =    "Further education";
my $LANGUAGES         =    "Languages";

my $HOBBIES           =    "Leisure hobbies";
my $TRAVEL            =    "Tourism / Travel";
my $HANDICRAF         =    "Handicraft";
my $MOTORING          =    "Motoring";
my $FITNESS           =    "Fitness and health";
my $COOKING           =    "Cooking";
my $SHOPPING          =    "Advertisement / Shopping";
my $GARDENING         =    "Gardening";

#
#

my %REPLACE=(

#    "fr:Fin des programmes" => 0 ,
    "en:Action"                => $ADVENTURE ,
    "en:Adventure"             => $ADVENTURE ,
    "en:Animals"               => $NATURE ,
    "en:Animated"              => $CARTOON ,
    "en:Artscrafts"            => $HOBBIES ,
    "en:Auto"                  => $MOTORING ,
    "en:Baseball"              => $SPORT_TEAM ,
    "en:Basketball"            => $SPORT_TEAM ,
    "en:Busfinancial"          => $NEWS_MAGAZINE ,
    "en:Children"              => $KIDS ,
    "en:Comedy"                => $COMEDY ,
    "en:Community"             => $RELIGION ,
    "en:Computers"             => $TECHNOLOGY ,
    "en:Consumer"              => $SHOPPING ,
    "en:Cooking"               => $COOKING ,
    "en:Crime"                 => $THRILLER ,
    "en:Crimedrama"            => $THRILLER ,
    "en:Drama"                 => $MOVIE,
    "en:Educational"           => $EDUCATIONAL,
    "en:Exercise"              => $FITNESS ,
    "en:Family"                => $KIDS ,
    "en:Fantasy"               => $SF ,
    "en:Fashion"               => $POPULAR_ART ,
    "en:Football"              => $FOOTBALL ,
    "en:Gameshow"              => $GAME ,
    "en:Golf"                  => $SPORT ,
    "en:Health"                => $FITNESS ,
    "en:History"               => $HISTORICAL ,
    "en:Hockey"                => $SPORT_TEAM ,
#    "en:Holiday"               => 0 ,
    "en:Homeimprovement"       => $SCIENCE ,
    "en:Horror"                => $SF ,
    "en:Housegarden"           => $GARDENING ,
#    "en:Howto"                 => $SCIENCE ,
    "en:Interview"             => $TALKSHOW ,
    "en:Medical"               => $MEDICINE ,
    "en:Motorsports"           => $SPORT_MOTOR ,
    "en:Movie"                 => $MOVIE ,
    "en:Music"                 => $MUSIC ,
    "en:Mystery"               => $THRILLER ,
    "en:Nature"                => $NATURE ,
    "en:News"                  => $NEWS ,
    "en:Newsmagazine"          => $MAGAZINE ,
    "en:Paranormal"            => $THRILLER ,
    "en:Performingarts"        => $PERFORMING ,
    "en:Playoffsports"         => $SPORT_TEAM ,
    "en:Politics"              => $SOCIAL ,
    "en:Prowrestling"          => $MARTIAL_ARTS ,
    "en:Publicaffairs"         => $DEBATE ,
    "en:Reality"               => $VARIETY ,
    "en:Religious"             => $RELIGION ,
    "en:Romance"               => $ROMANCE ,
#    "en:Science"               => $SCIENCE ,
    "en:Sciencefiction"        => $SF ,
    "en:Selfimprovement"       => $INTERVIEW ,
#    "en:Series"               => 0 ,
#    "en:Shooting"             => 0 ,
    "en:Shopping"              => $SHOPPING ,
    "en:Sitcom"                => $COMEDY ,
    "en:Soap"                  => $SOAP ,
    "en:Soccer"                => $FOOTBALL ,
    "en:Spanish"               => $LANGUAGES ,
    "en:Special"               => $RELIGION ,
    "en:Sports"                => $SPORT ,
    "en:Sportsnonevent"        => $SPORT_SPECIAL ,
    "en:Sportstalk"            => $SPORT_MAGAZINE ,
    "en:Suspense"              => $SF ,
    "en:Talk"                  => $TALKSHOW ,
    "en:Technology"            => $TECHNOLOGY ,
    "en:Travel"                => $TRAVEL ,
    "en:Thriller"              => $THRILLER ,
    "en:Weather"               => $WEATHER ,
    "en:Western"               => $ADVENTURE ,
 ) ; 


my $PRE  = '<category( lang=\"([a-z]+)\"|)>' ;
my $POST = '</category>'  ;

sub myfilter {
  my ($lang,$name) = @_;
  $name =~ s/\W//g;
  $lang="en"  if ( $lang eq "" ) ;   # Default language is "en" when is no lang attribute
  my $a = "$lang:$name" ; 
  if ( exists $REPLACE{$a} ) {     
      
      return $REPLACE{$a} ;
  } elsif ( $lang eq "en" ) {    
      print STDERR "Warning: Unmanaged category #1: '$a'\n" ;
      return $name ;   # For English, assume that missing entries are fine
  } else {
      print STDERR "Warning: Unmanaged category #2: '$a'\n" ;
      return $name ;
  }
}

# read the xml file and update the info
my $num_args = $#ARGV + 1;
if ($num_args != 1) {
  print STDERR "\nArg=$num_args Usage: <script> <xmlfile>\n";
  exit;
}
my $xmlfile=$ARGV[0];
my $parser=new XML::DOM::Parser;
print STDERR "Reading XML file\n";
my $doc=$parser->parsefile($xmlfile) or die$!;
print STDERR "Parsing Sections\n";
my $root=$doc->getDocumentElement();
my @program=$root->getElementsByTagName("programme");
foreach my $program(@program) {

  my $dateElement=$program->getElementsByTagName("date")->item(0);
  my $date;
  if ( defined $dateElement ) {
    $date=$dateElement->getFirstChild()->getData();
    if (length($date) == 8) {
      $date = substr($date,0,4) . "/" . substr($date,4,2) . "/" . substr($date,6,2);
    }
  }

  my $descadd='';
  if ( defined $date ) {
    $descadd='(' . $date . ') ';
  }
  my @episodenum=$program->getElementsByTagName("episode-num");
  my $se;
  foreach my $episodenum(@episodenum) {
    if ($episodenum->getAttribute("system") eq "common") {
      $se=$episodenum->getFirstChild()->getData();
    } elsif (($episodenum->getAttribute("system") eq "dd_progid") 
         && (!defined $se)) {

      my $dd_prog_id=$episodenum->getFirstChild()->getData();
      if ( $dd_prog_id =~ /^(..\d{8}).(\d{4})/ ) {
        # EP12345678.1234
        my $dd_e=$2;
        my $dd_s=$1;
        if (int($dd_e) > 0) {
          $se = sprintf("E%03d", int($dd_e));
        }
      }
    }
  }

  my @category=$program->getElementsByTagName("category");
  foreach my $category(@category) {
    $descadd=$descadd . $category->getFirstChild()->getData() . ' / ';
  }
  if ( defined $se ) {
    $descadd=$descadd . ' ' . $se;
  }

  # update the desc with year, season, episode and genre data
  my $descElement=$program->getElementsByTagName("desc")->item(0);
  my $desc='';
  if ( defined $descElement ) {
    $desc=$descElement->getFirstChild()->getData();
    $desc=$descadd . "\n" . $desc;
    $descElement->getFirstChild()->setNodeValue($desc);

  } else {
    if ( defined $descadd ) {
      # need to add a desc node
      $descElement=$doc->createElement('desc');
      my $textElement=$doc->createTextNode($descadd);
      $descElement->appendChild($textElement);
      $program->appendChild($descElement);
    }
  }

  # update subtitle with date
  my $subtitleElement=$program->getElementsByTagName("sub-title")->item(0);
  my $subtitle;
  if ( defined $subtitleElement ) {
    if (defined $se ) {
      $subtitle=$subtitleElement->getFirstChild()->getData();
      $subtitle=$se . ' ' . $subtitle;
      $subtitleElement->getFirstChild()->setNodeValue($subtitle);

#      my $catElement=$doc->createElement('category');
#      my $textElement2=$doc->createTextNode('Series');
#      $catElement->appendChild($textElement2);
#      $program->appendChild($catElement);
    }
  }

}
print STDERR "Pass 1 complete\n";
my $tempfile="/tmp/xmltv.xml_temp";
$doc->printToFile($tempfile);
$doc->dispose;
open(my $FN, '<', $tempfile) or die "unable to open file, $!";

print STDERR "Updating Genre\n";
while (<$FN>) {
    my $line = $_ ;
    # Warning $PRE contains 2 hidden level of parenthesis
    #  
    $line =~ s/($PRE)(.*)($POST)/"$1".myfilter($3,$4)."$5"/ge ;
    print $line;
} 
close($FN);
unlink $tempfile;
