This module keeps track of price changes made on pricelist items
(``product.pricelist.item``): rule creation, changes to the price fields
and rule deletion.

Every change is logged with the previous value, the new value, the user
who made it and the date. A chatter message is also posted on the related
product (or product template) so the change is visible in its history.

Once a day, a scheduled action sends a digest email per pricelist to the
users configured on that pricelist, respecting each user's notification
preference (email or internal Odoo notification only).
