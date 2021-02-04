$(document).ready(function(){
    var getConfigData = function(){
        $.getJSON("/config.json", function(json) {
            if (json != "Nothing found."){
               console.log(json);
               populateForm('#ConfigForm', json, null)
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
                            console.log(key+'='+value+" "+typeof value);
                            if ($(this).attr('value') == value) $(this).attr("checked",value);
                            $(this).prop("checked",value);
                        });
                        break;
                    case undefined:
                        console.log(key+" is undefined")
                        break;
                    case "text": case "hidden": case "password":
                        ctrl.val(value);
                        console.log(ctrl.prop("type")+' '+key+'='+value);
                        break;
                    default:
                        ctrl.val(value);
                        console.log(ctrl.prop("type")+' '+key+'='+value);

                }
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
