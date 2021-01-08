# © 2013-2016 Yannick Vaucher (Camptocamp SA)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
{
    "name": "Postlogistics Shipping",
    "summary": "Print postlogistics shipping labels",
    "version": "13.0.1.0.0",
    "author": "Camptocamp,Odoo Community Association (OCA)",
    "maintainer": "Camptocamp",
    "license": "AGPL-3",
    "category": "Delivery",
    "complexity": "normal",
    "depends": ["delivery", "mail", "base"],
    "website": "https://github.com/OCA/delivery-carrier",
    "data": [
        "data/partner.xml",
        "data/product.xml",
        "data/delivery.xml",
        "views/delivery.xml",
        "views/postlogistics_license.xml",
        "views/stock.xml",
        "security/ir.model.access.csv",
    ],
    "installable": True,
    "auto_install": False,
    "application": True,
}
