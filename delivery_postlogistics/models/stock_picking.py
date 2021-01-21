# Copyright 2013-2016 Camptocamp SA
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
import base64
from operator import attrgetter

from odoo import _, api, exceptions, fields, models

from ..postlogistics.web_service import PostlogisticsWebService


class StockPicking(models.Model):
    _inherit = "stock.picking"

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

    def _get_picking_postlogistic_packaging(self):
        """
        Get all the picking postlogistics service codes define in the picking
        """
        self.ensure_one()
        postlogistics_packages = self._get_packages_from_picking().filtered(
            lambda r: r.packaging_id
            and r.packaging_id.package_carrier_type == "postlogistics"
        )
        return postlogistics_packages.mapped("packaging_id")

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
                default_packaging = (
                    picking.carrier_id.postlogistics_default_packaging_id
                )
                package = self.env["stock.quant.package"].create(
                    {
                        "packaging_id": default_packaging
                        and default_packaging.id
                        or False
                    }
                )
                move_lines.write({"result_package_id": package.id})

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
