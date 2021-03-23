$(document).ready(function(){
    var getConfigData = function(){
        $.getJSON("/config.json", function(json) {
            if (json != "Nothing found."){
               populateForm('#ConfigForm', json, null)
               setDisplayLevel('#ConfigForm')
            } else {
                console.log(json);
                $('#status').html('<h2 class="loading">Were afraid nothing was returned. is the web interface disabled?</h2>');
            }
            return true;
        })
        .fail(function() {
                $('#status').html('<h2 class="loading">Unable to obtain config data. Is the config web interface disabled?</h2>');
                $('#save').prop("disabled",true);
                return false;
        })
        return false;
    }
    
    function populateForm(form,data,parent) {
        $.each(data, function(key, value) {
            if(value !== null && typeof value === 'object' ) {
                populateForm(form,value,key+'-')
            } else {
                if (parent === null) {
                    var ctrl = $('[name='+key+']', form);
                } else {
                    var ctrl = $('[name='+parent+key+']', form);
                }
                switch(ctrl.prop("type")) {
                    case "radio": case "checkbox":
                        ctrl.each(function() {
                            if ($(this).attr('value') == value) $(this).attr("checked",value);
                            $(this).prop("checked",value);
                        });
                        break;
                    case undefined:
                        console.log(key+" The type is undefined")
                        break;
                    case "text": case "hidden": case "password":
                        ctrl.val(value);
                        vallength = value.length+5
                        if (vallength < 15) {
                            vallength = 15
                        }
                        ctrl.attr('size', vallength)
                        break;
                    default:
                        ctrl.val(value);
                }
            }
        });
        $('form select:first').on('change', function() {
            setDisplayLevel();
        });

    }

    function setDisplayLevel() {
        var currentLevelValue = $('form select:first').val()
        if (currentLevelValue == '') {
            currentLevelValue = '1-Standard'
        }
        var currentLevel = currentLevelValue.match(/^\d+/)[0];
        $('form tr[class^="dlevel"]').each(
            function(index) {
                var input = $(this)
                var itemLevel = input.attr('class').match(/\d+$/)[0];
                if (itemLevel > currentLevel) {
                    $(this).hide()
                } else {
                    $(this).show()
                }
        });
        $('tr[class="dsection"]').each(
            function(index) {
                if ( $(this).parent().next().children(':visible').length == 0) {
                    $(this).hide()
                } else {
                    $(this).show()
                }
        });
    }
    getConfigData();
    $('#ConfigForm').submit(function() { // catch the form's submit
        $.ajax({
            data: $(this).serialize(),
            type: $(this).attr('method'), // GET or POST
            url: $(this).attr('action'),
            success: function(response) { // on success
                $('#status').html(response);
            }
        });
        return false; // cancel original submit event
    });
});
