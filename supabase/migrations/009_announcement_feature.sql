-- Migration 009: Announcement feature catalog entry
-- Required by the Announcement Broadcast workflow for education_log FK.

INSERT INTO feature_catalog (id, display_name, description, how_to_use, category)
VALUES (
    'announcement',
    'Announcements',
    'Broadcast messages from admins through personalized assistants.',
    'Admin-only: DM "announce: <message>" to broadcast.',
    'core'
)
ON CONFLICT (id) DO NOTHING;
