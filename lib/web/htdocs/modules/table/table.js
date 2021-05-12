(function(){
	// https://www.colorzilla.com/gradient-editor/
	/**
	 * Simple and unobtrusive "plugin" for tablesorter
	 * 
	 * Automatically adds a search input and filters the
	 * table rows on keyup.
	 *
	 */
	jQuery.extend({
		tablesorterSearch: new
		function() {
			
			/*
			 * Case insensitive matching function
			 * 
			 * Returns an array of jquery objects for each matching row
			 */ 
			function performSearch( term, table ) {
				
				var results = [];
				
				if( term.length ) {
					
					// will contain an array of tr jquery objects
					var allrows = table.config.originalRows,
						term = term.toLowerCase(), i, $row, col_text;
				
					for(  i = 0; i < allrows.length; i++ ) {
						$row = allrows[i];
						
						jQuery('td', $row).each( function(){
							
							col_text = jQuery(this).text().toLowerCase();
							
							if( col_text.indexOf(term) !== -1 ) {
								
								// Match found, push row and break
								results.push( $row );
								return false;
							}
						});
						
					}
					
					
				} else {
					
					// No term present -- reset to unfiltered table list
					results = table.config.originalRows;
					
				}

				// Update cache with new rows
				jQuery(table).trigger('update');
				
				// Wait for cache update to complete and then reapply sorts and widgets
				setTimeout( function(){

					// If user had a sort in use, reapply it to filtered results
					if( table.config.sortList.length )
						jQuery(table).trigger('sorton', [ table.config.sortList ] );

					// Apply widgets		
					jQuery(table).trigger('applyWidgets');

				}, 1 );

				// Render results
				renderTable( table, results );
				
			}

			/*
				 * Update table given an array of rows
				 */ 
			function renderTable(table,rows) {
				
				var $tableBody = jQuery(table.tBodies[0]);
				
				jQuery.tablesorter.clearTableBody(table);
				
				for(var i = 0; i < rows.length; i++) {
					
					var o = rows[i];
					var l = o.length;
					for(var j=0; j < l; j++) {
						
						$tableBody[0].appendChild(o[j]);

					}
				}
				
			}


			/*
				 * Store original rows in table config object
				 */ 
			this.appender = function( table, rows ) {

				if( typeof( table.config.originalRows ) == 'undefined' ) {
					table.config.originalRows = rows;
				}

				renderTable( table, rows );
				
			}

			/*
				 * Additional settings to merge with tablesorter
				 */
			this.defaults = {
				containerClass: 'tablesorterSearch',
				inputClass: 'search',
				placeholderText: 'Search table...',
				appender: this.appender
			};
			
			this.construct = function( settings ) {
				return this.each( function () {
					var table = this, $table = jQuery(this);
					var config = jQuery.extend( table.config, jQuery.tablesorterSearch.defaults, settings);

					// Add our custom sauce
					$table.trigger("appendCache");

					// Append search container and input field
					var $container = jQuery('<div class="'+config.containerClass+'"></div>');
					var $input = jQuery('<input type="text" class="'+config.inputClass+'" placeholder="'+config.placeholderText+'">').appendTo($container);
					$table.before($container);

					// Search on key up
					$input.keyup(function(e){
						var term = jQuery.trim( jQuery(this).val() );
						performSearch( term, table );
					});
					
				});
			}
		}
	});

	// extend plugin scope
	jQuery.fn.extend({
		tablesorterSearch: jQuery.tablesorterSearch.construct
	});
		
})();

(function($) {

	var i = 0;
	
	/* Firefox sometimes doesn't draw bg images unless something forces redraw */
	function ffSortableFix() {
		var $headers = $('.sortable .header'), bg;
		$headers.css('opacity', '0.99');
		setTimeout(function() {
			$headers.css('opacity', '1');
		},500);
		
	}
	
	/* Once tablesorter is loaded, instantiate tablesorter objects */
	function initTableSorter() {
		if( $.tablesorter ) {
			$('.sortable').not('.searchable').tablesorter();

			if( $.tablesorterSearch ) {
				$('.sortable.searchable').tablesorter({'widthFixed': true}).tablesorterSearch({'containerClass': 'searchable-header'});
			}
			
			/* try to limit this fix to FF */
			if (navigator.userAgent.toLowerCase().indexOf('firefox') > -1) {
				ffSortableFix();
			}
		} else {
			if (i < 5) {
				setTimeout(function() {
					initTableSorter();
				}, 100);
				i++;
			}
		}
	}
	
	initTableSorter();

})(jQuery);