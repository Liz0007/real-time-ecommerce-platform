# Order & Payment FAQ

## Order statuses
An order can be in one of three states:

- **pending** — the order was created and payment/inventory checks are still
  in progress.
- **confirmed** — payment succeeded AND inventory was successfully reserved.
  Both conditions must be true for an order to be confirmed.
- **cancelled** — either the payment failed or inventory was unavailable.
  If either check fails, the order is automatically cancelled; it does not
  stay pending waiting for a retry.

## Payment and inventory checks run in parallel
When an order is placed, payment processing and inventory reservation are
checked independently and at the same time — not one after the other. Because
they run in parallel, either one can complete first. The order is only
confirmed once both checks have finished and both succeeded.

## Failed payments
If a payment fails, the payment record includes a specific failure reason,
such as `insufficient_funds`, `card_declined`, or `provider_timeout`. A failed
payment immediately cancels the order — there is no retry window or pending
period.

## Inventory reservations
If inventory is successfully reserved for an order, the reservation holds for
15 minutes from the time it was made. This is tracked as an expiry deadline
on the reservation record.

Note: automatic release of expired, unconfirmed reservations back to
available stock is not yet implemented. An expired reservation's deadline is
recorded, but the reservation itself is not automatically released at this
time.

## Cancellations and refunds
There is currently no customer-initiated cancellation or refund process.
Orders are only cancelled automatically, as a result of a failed payment or
unavailable inventory check.
