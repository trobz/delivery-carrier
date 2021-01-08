# Copyright 2013-2016 Camptocamp SA
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models

POSTLOGISTIC_TYPES = [
    ("label_layout", "Label Layout"),
    ("output_format", "Output Format"),
    ("resolution", "Output Resolution"),
    ("basic", "Basic Service"),
    ("additional", "Additional Service"),
    ("delivery", "Delivery Instructions"),
]


class DeliveryCarrierTemplateOption(models.Model):
    """ Available options for a carrier (partner) """

    _name = "postlogistics.delivery.carrier.template.option"
    _description = "Delivery carrier template option"

    partner_id = fields.Many2one(comodel_name="res.partner", string="Partner Carrier")
    name = fields.Char(translate=True)
    code = fields.Char()
    description = fields.Char(
        help="Allow to define a more complete description than in the name field.",
    )
    postlogistics_type = fields.Selection(
        selection=POSTLOGISTIC_TYPES, string="PostLogistics option type",
    )
    # relation tables to manage compatiblity between basic services
    # and other services
    postlogistics_basic_service_ids = fields.Many2many(
        comodel_name="postlogistics.delivery.carrier.template.option",
        relation="postlogistics_compatibility_service_rel",
        column1="service_id",
        column2="basic_service_id",
        string="Basic Services",
        domain=[("postlogistics_type", "=", "basic")],
        help="List of basic service for which this service is compatible",
    )
    postlogistics_additonial_service_ids = fields.Many2many(
        comodel_name="postlogistics.delivery.carrier.template.option",
        relation="postlogistics_compatibility_service_rel",
        column1="basic_service_id",
        column2="service_id",
        string="Compatible Additional Services",
        domain=[("postlogistics_type", "=", "additional")],
    )
    postlogistics_delivery_instruction_ids = fields.Many2many(
        comodel_name="postlogistics.delivery.carrier.template.option",
        relation="postlogistics_compatibility_service_rel",
        column1="basic_service_id",
        column2="service_id",
        string="Compatible Delivery Instructions",
        domain=[("postlogistics_type", "=", "delivery")],
    )
