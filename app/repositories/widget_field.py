# app/repositories/widget_field.py
import uuid
from typing import Optional
from sqlalchemy.orm import Session, joinedload
from app.models.widget_field import WidgetField
from app.models.field_definition import FieldDefinition

class WidgetFieldRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_for_widget(self, widget_id: uuid.UUID) -> list[WidgetField]:
        return (
            self.db.query(WidgetField)
            .options(joinedload(WidgetField.field_definition))
            .filter(WidgetField.widget_id == widget_id)
            .order_by(WidgetField.display_order.asc())
            .all()
        )

    def get_by_widget_and_field(
        self, widget_id: uuid.UUID, field_id: uuid.UUID
    ) -> Optional[WidgetField]:
        return (
            self.db.query(WidgetField)
            .options(joinedload(WidgetField.field_definition))
            .filter(
                WidgetField.widget_id == widget_id,
                WidgetField.field_id == field_id,
            )
            .first()
        )

    def get_by_id(self, widget_field_id: uuid.UUID) -> Optional[WidgetField]:
        return (
            self.db.query(WidgetField)
            .options(joinedload(WidgetField.field_definition))
            .filter(WidgetField.widget_field_id == widget_field_id)
            .first()
        )

    def set_fields_for_widget(
        self,
        widget_id: uuid.UUID,
        field_configs: list[dict],
    ) -> list[WidgetField]:
        """
        Replaces the configured fields for a widget atomically.
        """
        # Delete existing fields
        self.db.query(WidgetField).filter(WidgetField.widget_id == widget_id).delete()
        self.db.flush()

        created = []
        for cfg in field_configs:
            wf = WidgetField(
                widget_id=widget_id,
                field_id=cfg["field_id"],
                display_order=cfg["display_order"],
                required=cfg["required"],
            )
            self.db.add(wf)
            created.append(wf)

        self.db.flush()
        return self.list_for_widget(widget_id)

    def add_field(
        self, widget_id: uuid.UUID, field_id: uuid.UUID, display_order: int, required: bool
    ) -> WidgetField:
        wf = WidgetField(
            widget_id=widget_id,
            field_id=field_id,
            display_order=display_order,
            required=required,
        )
        self.db.add(wf)
        self.db.flush()
        return wf

    def update_field(
        self,
        widget_field: WidgetField,
        display_order: Optional[int] = None,
        required: Optional[bool] = None,
    ) -> WidgetField:
        if display_order is not None:
            widget_field.display_order = display_order
        if required is not None:
            widget_field.required = required
        self.db.flush()
        return widget_field

    def delete(self, widget_field: WidgetField) -> None:
        self.db.delete(widget_field)
        self.db.flush()