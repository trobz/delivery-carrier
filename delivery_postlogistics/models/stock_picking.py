# Copyright 2013-2016 Camptocamp SA
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import base64
from operator import attrgetter

from odoo import _, api, exceptions, fields, models

from ..postlogistics.web_service import PostlogisticsWebService


class StockPicking(models.Model):
    _inherit = "stock.picking"

    postlogistics_option_ids = fields.Many2many(
        comodel_name="postlogistics.delivery.carrier.option", string="Options"
    )

    delivery_fixed_date = fields.Date(
        "Fixed delivery date", help="Specific delivery date (ZAW3217)"
    )
    delivery_place = fields.Char(
        "Delivery Place", help="For Deposit item service (ZAW3219)"
    )
    delivery_phone = fields.Char(
        "Phone", help="For notify delivery by telephone (ZAW3213)"
    )
    delivery_mobile = fields.Char(
        "Mobile", help="For notify delivery by telephone (ZAW3213)"
    )

    @api.onchange("carrier_id")
    def onchange_carrier_id(self):
        """ Inherit this method in your module """
        if not self.carrier_id:
            return
        # This can look useless as the field carrier_code and
        # carrier_type are related field. But it's needed to fill
        # this field for using this fields in the view. Indeed the
        # module that depend of delivery base can hide some field
        # depending of the type or the code
        carrier = self.carrier_id
        self.update({"delivery_type": carrier.delivery_type})
        default_options = carrier.default_options()
        self.postlogistics_option_ids = default_options
        result = {
            "domain": {
                "postlogistics_option_ids": [
                    ("id", "in", carrier.postlogistics_available_option_ids.ids)
                ]
            }
        }
        return result

    @api.onchange("postlogistics_option_ids")
    def onchange_postlogistics_option_ids(self):
        if not self.carrier_id:
            return
        carrier = self.carrier_id
        for available_option in carrier.postlogistics_available_option_ids:
            if (
                available_option.mandatory
                and available_option not in self.postlogistics_option_ids
            ):
                # XXX the client does not allow to modify the field that
                # triggered the onchange:
                # https://github.com/odoo/odoo/issues/2693#issuecomment-56825399
                # Ideally we should add the missing option
                raise exceptions.UserError(
                    _(
                        "You should not remove a mandatory option."
                        "Please cancel the edit or "
                        "add back the option: %s."
                    )
                    % available_option.name
                )

    @api.model
    def _values_with_carrier_options(self, values):
        values = values.copy()
        carrier_id = values.get("carrier_id")
        option_ids = values.get("postlogistics_option_ids")
        if carrier_id and not option_ids:
            carrier_obj = self.env["delivery.carrier"]
            carrier = carrier_obj.browse(carrier_id)
            default_options = carrier.default_options()
            if default_options:
                values.update(postlogistics_option_ids=[(6, 0, default_options.ids)])
        return values

    def write(self, vals):
        """ Set the default options when the delivery method is changed.

        So we are sure that the options are always in line with the
        current delivery method.

        """
        vals = self._values_with_carrier_options(vals)
        return super().write(vals)

    @api.model
    def create(self, vals):
        """ Trigger onchange_carrier_id on create

        To ensure options are setted on the basis of carrier_id copied from
        Sale order or defined by default.

        """
        vals = self._values_with_carrier_options(vals)
        return super().create(vals)

    def _get_packages_from_picking(self):
        """ Get all the packages from the picking """
        self.ensure_one()
        operation_obj = self.env["stock.move.line"]
        packages = self.env["stock.quant.package"].browse()
        operations = operation_obj.search(
            [
                "|",
                ("package_id", "!=", False),
                ("result_package_id", "!=", False),
                ("picking_id", "=", self.id),
            ]
        )
        for operation in operations:
            # Take the destination package. If empty, the package is
            # moved so take the source one.
            packages |= operation.result_package_id or operation.package_id
        return packages

    def get_shipping_label_values(self, label):
        self.ensure_one()
        return {
            "name": label["name"],
            "res_id": self.id,
            "res_model": "stock.picking",
            "datas": label["file"],
            "file_type": label["file_type"],
        }

    def attach_shipping_label(self, label):
        """Attach a label returned by generate_shipping_labels to a picking"""
        self.ensure_one()
        data = self.get_shipping_label_values(label)
        if label.get("package_id"):
            data["package_id"] = label["package_id"]
            if label.get("tracking_number"):
                self.env["stock.quant.package"].browse(label["package_id"]).write(
                    {"parcel_tracking": label.get("tracking_number")}
                )
        context_attachment = self.env.context.copy()
        # remove default_type setted for stock_picking
        # as it would try to define default value of attachement
        if "default_type" in context_attachment:
            del context_attachment["default_type"]
        return (
            self.env["postlogistics.shipping.label"]
            .with_context(context_attachment)
            .create(data)
        )

    def _set_a_default_package(self):
        """ Pickings using this module must have a package
            If not this method put it one silently
        """
        for picking in self:
            move_lines = picking.move_line_ids.filtered(
                lambda s: not (s.package_id or s.result_package_id)
            )
            if move_lines:
                package = self.env["stock.quant.package"].create({})
                move_lines.write({"result_package_id": package.id})

    def send_to_shipper(self):
        super().send_to_shipper()
        if self.delivery_type == "postlogistics":
            self.postlogistics_send_shipping()

    def postlogistics_send_shipping(self):
        """
        It will generate the labels for all the packages of the picking.
        Packages are mandatory in this case
        """
        for pick in self:
            pick._set_a_default_package()
            shipping_labels = pick._generate_postlogistics_label()
            for label in shipping_labels:
                pick.attach_shipping_label(label)
        return True

    def postlogistics_cod_amount(self):
        """ Return the Postlogistic Cash on Delivery amount of a picking

        If the picking delivers the whole sales order, we use the total
        amount of the sales order.

        Otherwise, we don't know the value of each picking so we raise
        an error.  The user has to create packages with the cash on
        delivery price on each package.
        """
        self.ensure_one()
        order = self.sale_id
        if not order:
            return 0.0
        if len(order) > 1:
            raise exceptions.Warning(
                _(
                    "The cash on delivery amount must be manually specified "
                    "on the packages when a package contains products "
                    "from different sales orders."
                )
            )
        order_moves = order.mapped("order_line.procurement_ids.move_ids")
        picking_moves = self.move_lines
        # check if the package delivers the whole sales order
        if order_moves != picking_moves:
            raise exceptions.Warning(
                _(
                    "The cash on delivery amount must be manually specified "
                    "on the packages when a sales order is delivered "
                    "in several delivery orders."
                )
            )
        return order.amount_total

    def write_tracking_number_label(self, label_result, packages):
        """
        if there are no pack defined, write tracking_number on picking
        otherwise, write it on parcel_tracking field of each pack
        """

        def info_from_label(label):
            tracking_number = label["tracking_number"]
            return {
                "file": base64.b64decode(label["binary"]),
                "file_type": label["file_type"],
                "name": tracking_number + "." + label["file_type"],
            }

        labels = []
        if not packages:
            label = label_result["value"][0]
            tracking_number = label["tracking_number"]
            self.carrier_tracking_ref = tracking_number
            info = info_from_label(label)
            info["package_id"] = False
            labels.append(info)
            return labels

        tracking_refs = []
        for package in packages:
            label = None
            for search_label in label_result["value"]:
                if package.name in search_label["item_id"].split("+")[-1]:
                    label = search_label
                    tracking_number = label["tracking_number"]
                    package.parcel_tracking = tracking_number
                    tracking_refs.append(tracking_number)
                    break
            info = info_from_label(label)
            info["package_id"] = package.id
            labels.append(info)

        self.carrier_tracking_ref = "; ".join(tracking_refs)
        return labels

    def _generate_postlogistics_label(self, webservice_class=None, package_ids=None):
        """ Generate labels and write tracking numbers received """
        self.ensure_one()
        user = self.env.user
        company = user.company_id
        if webservice_class is None:
            webservice_class = PostlogisticsWebService

        if package_ids is None:
            packages = self._get_packages_from_picking()
            packages = sorted(packages, key=attrgetter("name"))
        else:
            # restrict on the provided packages
            package_obj = self.env["stock.quant.package"]
            packages = package_obj.browse(package_ids)

        web_service = webservice_class(company)
        label_result = web_service.generate_label(self, packages, user_lang=user.lang)

        if "errors" in label_result:
            raise exceptions.Warning("\n".join(label_result["errors"]))

        labels = self.write_tracking_number_label(label_result, packages)
        return labels

    def generate_postlogistics_shipping_labels(self, package_ids=None):
        """ Add label generation for Postlogistics """
        self.ensure_one()
        return self._generate_postlogistics_label(package_ids=package_ids)
