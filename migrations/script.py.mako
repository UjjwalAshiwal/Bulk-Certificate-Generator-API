"""Mako template (unused; env.py uses no templating)."""
revision = "${up_revision}"
down_revision = ${down_revision}
branch_labels = ${branch_labels}
depends_on = ${depends_on}
def upgrade(): ${upgrades}
def downgrade(): ${downgrades}
