$(document).ready(function(){

    $('form').submit(function() { // catch the form's submit
        $(this).find('input[type="checkbox"]').each(function() {
            if ($(this).is(":checked") == true) {
                var n = '#'+$(this).attr("id")+'hidden';
                $(n).prop("disabled", true);
            } else {
                var n = '#'+$(this).attr("id")+'hidden';
                $(n).prop("disabled", false);
            }
        });

        if ( $('input[name=sort_dir]').val() ) {
            console.log('it is not empty');
            $.ajax({
                data: $(this).serialize(),
                type: $(this).attr('method'), // GET or POST
                url: $(this).attr('action'),
                success: function(response) { // on success
                    $('#tablecontent').html(response);
                }
            });
        } else {
            console.log('it is empty');
            $.ajax({
                data: $(this).serialize(),
                type: $(this).attr('method'), // GET or POST
                url: $(this).attr('action'),
                success: function(response) { // on success
                    $('#status').html(response);
                }
            });
        }

        return false; // cancel original submit event
    });
});
