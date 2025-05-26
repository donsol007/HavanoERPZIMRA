// Copyright (c) 2025, Donsol and contributors
// For license information, please see license.txt

// frappe.ui.form.on("Openday", {
// 	refresh(frm) {

// 	},
// });

frappe.ui.form.on('Openday', {
    refresh: function(frm) {
        //.page.set_primary_action('', () => {}); // Empty label and action
        frm.page.btn_primary.hide();
        frm.add_custom_button(__('Open Day'), function() {
            // Show a temporary "Processing..." message
            let processing_msg = frappe.msgprint(__('Opening Fiscal day...'), 'Please wait');

            // Call the server method
            frappe.call({
                method: 'havanozimra.havanozimra.controller.HavanoZimra.openday',
                args: { docname: frm.doc.name },
                callback: function(response) {
                    // Delay for 2 seconds (2000ms) before showing the result
                    setTimeout(() => {
                        frappe.hide_msgprint(processing_msg); // Hide "Processing..."
                        if (response.message) {
                            frappe.msgprint({
                                title: __('Success'),
                                indicator: 'green',
                                message: response.message
                            });
                            frm.refresh();
                        }
                    }, 1000); // Adjust delay time here (in milliseconds)
                },
                error: function(error) {
                    setTimeout(() => {
                        frappe.hide_msgprint(processing_msg); // Hide "Processing..."
                        frappe.msgprint({
                            title: __('Error'),
                            indicator: 'red',
                            message: "Error opening fiscal day: " + error
                        });
                    }, 1000);
                }
            });
        });
    }
});
