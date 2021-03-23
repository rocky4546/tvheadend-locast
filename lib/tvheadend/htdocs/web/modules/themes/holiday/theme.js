$(document).ready(setTimeout(function(){
    var images = ['bg1.jpg', 'bg2.jpg', 'bg3.jpg', 'bg4.jpg'];
    var randnum  = Math.floor(Math.random() * images.length);
    $('.backgroundContainer').css({'background-image': 'linear-gradient( var(--theme-background), var(--theme-background) ),  url(modules/themes/holiday/' + images[randnum] + ')'});
}, 100));
