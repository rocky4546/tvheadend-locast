$(document).ready(setTimeout(function() {
    $('table.sortable th img.sortit').each(function() {
        $(this).click(function() {
            if ( $(this).hasClass("sortnone") ) {
                console.log('sort none ', $(this).parent().text());
                newDirection = 'sortasc';
            } else if ( $(this).hasClass("sortasc") ) {
                console.log('sort asc', $(this).parent().text());
                newDirection = 'sortdesc';
            } else if ( $(this).hasClass("sortdesc") ) {
                console.log('sort desc', $(this).parent().text());
                newDirection = 'sortnone';
            } else {
                console.log('sort missing using ascending', $(this).parent().text());
                newDirection = 'sortasc';
            }
            text = $(this).parent().text();
            if (!text) {
                text = $(this).parent().parent().find("input").attr("id");
            }
            $('input[name=sort_col]').val(text)
            $('input[name=sort_dir]').val(newDirection)
            $('form:first').submit()
            $('input[name=sort_col]').val(null)
            $('input[name=sort_dir]').val(null)
        });
    });
    $('table.sortable th input[type=checkbox]').each(function() {
        $(this).change(function() {
            console.log("the input checkbox changed");
        });
    });
        
}, 1000));
