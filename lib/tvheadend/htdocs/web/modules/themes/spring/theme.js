$(document).ready(setTimeout(function(){
    var images = ['bg1.jpg', 'bg2.jpg', 'bg3.jpg', 'bg4.jpg', 'bg5.jpg'];
    var randnum  = Math.floor(Math.random() * images.length);
    $('.backgroundContainer').css({'background-image': 'linear-gradient( var(--theme-background), var(--theme-background) ),  url(modules/themes/spring/' + images[randnum] + ')'});
}, 100));
