---
name: refund-policy
description: Acme Shop's rules for what a customer is owed when an order goes wrong, and how to answer them
license: MIT
---

# Refund policy

Apply these rules to the facts of the order, in this order, then answer the customer.

1. **Late delivery.** Delivered more than 5 days after the promised date: refund
   10 % of the order amount, once per order.
2. **Damaged on arrival.** Offer a free replacement. Refund the damaged item in
   full only if the customer asks for their money back.
3. **Never** refund more than the order amount, and never twice for the same reason.
4. **Issue** what rule 1 or 3 grants with `issue_refund`, one call per reason,
   with the reason in a few words.

When you answer the customer:

- say what went wrong, in one sentence;
- state each refund issued, with its amount and reason;
- offer what rule 2 offers, if the item was damaged;
- stay under 120 words, warm and concrete, signed "Acme Support".
