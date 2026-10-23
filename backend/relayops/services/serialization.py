from sqlalchemy import select
from relayops.models import Attempt, Delivery, Destination, DispatchStart
from relayops.services.policy import event_status


def serialize(model, exclude=()):
    return {
        column.name: getattr(model, column.name)
        for column in model.__table__.columns
        if column.name not in exclude
    }


async def delivery_json(db, delivery, attempts=False):
    result = serialize(delivery, ("lease_owner", "lease_version", "lease_until"))
    destination = await db.get(Destination, delivery.destination_id)
    result["destination_name"] = destination.name if destination else "Deleted destination"
    if attempts:
        rows = (
            await db.scalars(
                select(Attempt).where(Attempt.delivery_id == delivery.id).order_by(Attempt.started_at)
            )
        ).all()
        result["attempts"] = [serialize(a) for a in rows]
        starts = (
            await db.scalars(
                select(DispatchStart)
                .where(DispatchStart.delivery_id == delivery.id)
                .order_by(DispatchStart.started_at)
            )
        ).all()
        observed = {a.number for a in rows}
        result["dispatches"] = [{**serialize(s), "outcome_recorded": s.number in observed} for s in starts]
    return result


async def event_json(db, event, detailed=False):
    deliveries = (await db.scalars(select(Delivery).where(Delivery.event_id == event.id))).all()
    result = serialize(event, ("payload_hash", "trace_context", "idempotency_key"))
    result["status"] = event_status([d.status for d in deliveries])
    result["delivery_count"] = len(deliveries)
    if detailed:
        result["deliveries"] = [await delivery_json(db, d, True) for d in deliveries]
    else:
        result.pop("payload")
    return result
