# Copyright 2013-2016 Camptocamp SA
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class DeliveryCarrier(models.Model):
    """ Add service group """

    _inherit = "delivery.carrier"

    delivery_type = fields.Selection(
        selection_add=[("postlogistics", "Post logistics")]
    )
    allowed_postlogistics_tmpl_options_ids = fields.Many2many(
        "postlogistics.delivery.carrier.template.option",
        compute="_compute_allowed_options_ids",
        store=False,
    )
    postlogistics_endpoint_url = fields.Char(
        string="Endpoint URL", default="https://wedecint.post.ch/", required=True,
    )
    postlogistics_client_id = fields.Char(
        string="Client ID", groups="base.group_system"
    )
    postlogistics_client_secret = fields.Char(
        string="Client Secret", groups="base.group_system"
    )
    postlogistics_logo = fields.Binary(
        string="Company Logo on Post labels",
        help="Optional company logo to show on label.\n"
        "If using an image / logo, please note the following:\n"
        "– Image width: 47 mm\n"
        "– Image height: 25 mm\n"
        "– File size: max. 30 kb\n"
        "– File format: GIF or PNG\n"
        "– Colour table: indexed colours, max. 200 colours\n"
        "– The logo will be printed rotated counter-clockwise by 90°"
        "\n"
        "We recommend using a black and white logo for printing in "
        " the ZPL2 format.",
    )
    postlogistics_office = fields.Char(
        string="Domicile Post office",
        help="Post office which will receive the shipped goods",
    )

    postlogistics_label_layout = fields.Many2one(
        comodel_name="postlogistics.delivery.carrier.template.option",
        string="Default label layout",
        domain=[("postlogistics_type", "=", "label_layout")],
    )
    postlogistics_output_format = fields.Many2one(
        comodel_name="postlogistics.delivery.carrier.template.option",
        string="Default output format",
        domain=[("postlogistics_type", "=", "output_format")],
    )
    postlogistics_resolution = fields.Many2one(
        comodel_name="postlogistics.delivery.carrier.template.option",
        string="Default resolution",
        domain=[("postlogistics_type", "=", "resolution")],
    )
    postlogistics_tracking_format = fields.Selection(
        [
            ("postlogistics", "Use default postlogistics tracking numbers"),
            ("picking_num", "Use picking number with pack counter"),
        ],
        string="Tracking number format",
        default="postlogistics",
        help="Allows you to define how the ItemNumber (the last 8 digits) "
        "of the tracking number will be generated:\n"
        "- Default postlogistics numbers: The webservice generates it"
        " for you.\n"
        "- Picking number with pack counter: Generate it using the "
        "digits of picking name and add the pack number. 2 digits for"
        "pack number and 6 digits for picking number. (eg. 07000042 "
        "for picking 42 and 7th pack",
    )
    postlogistics_proclima_logo = fields.Boolean(
        "Print ProClima logo",
        help="The “pro clima” logo indicates an item for which the "
        "surcharge for carbon-neutral shipping has been paid and a "
        "contract to that effect has been signed. For Letters with "
        "barcode (BMB) domestic, the ProClima logo is printed "
        "automatically (at no additional charge)",
    )

    postlogistics_available_option_ids = fields.One2many(
        comodel_name="postlogistics.delivery.carrier.option",
        inverse_name="carrier_id",
        string="Options",
        context={"active_test": False},
    )

    postlogistics_license_id = fields.Many2one(
        comodel_name="postlogistics.license", string="Franking License",
    )
    postlogistics_basic_service_ids = fields.One2many(
        comodel_name="postlogistics.delivery.carrier.template.option",
        compute="_compute_basic_service_ids",
        string="Service Group",
        help="Basic Service defines the available "
        "additional options for this delivery method",
    )

    @api.onchange("prod_environment")
    def onchange_prod_environment(self):
        """
        Auto change the end point url following the environment
        - Test: https://wedecint.post.ch/
        - Prod: https://wedec.post.ch/
        """
        for carrier in self:
            if carrier.prod_environment:
                carrier.postlogistics_endpoint_url = "https://wedec.post.ch/"
            else:
                carrier.postlogistics_endpoint_url = "https://wedecint.post.ch/"

    def default_options(self):
        """ Returns default and available options for a carrier """
        options = self.env["postlogistics.delivery.carrier.option"].browse()
        for available_option in self.postlogistics_available_option_ids:
            if available_option.mandatory or available_option.by_default:
                options |= available_option
        return options

    @api.depends(
        "delivery_type",
        "postlogistics_available_option_ids",
        "postlogistics_available_option_ids.tmpl_option_id",
        "postlogistics_available_option_ids.postlogistics_type",
    )
    def _compute_basic_service_ids(self):
        """ Search in all options for PostLogistics basic services if set """
        for carrier in self:
            if carrier.delivery_type == "postlogistics":
                options = carrier.postlogistics_available_option_ids.filtered(
                    lambda option: option.postlogistics_type == "basic"
                ).mapped("tmpl_option_id")

                carrier.postlogistics_basic_service_ids = options or None
            else:
                # Prevent CacheMiss exception
                carrier.postlogistics_basic_service_ids = None

    @api.depends(
        "delivery_type",
        "postlogistics_basic_service_ids",
        "postlogistics_available_option_ids",
        "postlogistics_available_option_ids.postlogistics_type",
    )
    def _compute_allowed_options_ids(self):
        """ Compute allowed delivery.carrier.option.

        We do this to ensure the user first select a basic service. And
        then he adds additional services.
        """
        option_template_obj = self.env["postlogistics.delivery.carrier.template.option"]

        for carrier in self:
            allowed = option_template_obj.browse()
            domain = []
            if carrier.delivery_type != "postlogistics":
                domain.append(("partner_id", "=", False))
            else:
                basic_services = carrier.postlogistics_basic_service_ids
                if basic_services:
                    related_services = option_template_obj.search(
                        [("postlogistics_basic_service_ids", "in", basic_services.ids)]
                    )
                    allowed |= related_services

                # Allows to set multiple optional single option in order to
                # let the user select them
                single_option_types = [
                    "label_layout",
                    "output_format",
                    "resolution",
                ]
                selected_single_options = [
                    opt.tmpl_option_id.postlogistics_type
                    for opt in carrier.postlogistics_available_option_ids
                    if opt.postlogistics_type in single_option_types and opt.mandatory
                ]
                if selected_single_options != single_option_types:
                    services = option_template_obj.search(
                        [
                            ("postlogistics_type", "in", single_option_types),
                            ("postlogistics_type", "not in", selected_single_options),
                        ],
                    )
                    allowed |= services
                partner = self.env.ref(
                    "delivery_postlogistics" ".partner_postlogistics"
                )
                domain.append(("partner_id", "=", partner.id)),
                domain.append(("id", "in", allowed.ids))

            carrier.allowed_postlogistics_tmpl_options_ids = option_template_obj.search(
                domain
            )

    def postlogistics_get_tracking_link(self, picking):
        return (
            "https://service.post.ch/EasyTrack/"
            "submitParcelData.do?formattedParcelCodes=%s" % picking.carrier_tracking_ref
        )

    def postlogistics_cancel_shipment(self, pickings):
        raise NotImplementedError()
