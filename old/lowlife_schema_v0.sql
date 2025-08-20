
-- Lowlife schema v0 (PostgreSQL)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE districts (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  name text NOT NULL UNIQUE,
  pd_rating integer DEFAULT 50,
  hazards jsonb DEFAULT '{}'::jsonb
);

CREATE TABLE factions (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  name text NOT NULL UNIQUE,
  description text
);

CREATE TABLE players (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  alias text NOT NULL UNIQUE,
  legal_name text,
  home_district_id uuid REFERENCES districts(id),
  birth_packet jsonb DEFAULT '{}'::jsonb,
  created_at timestamptz DEFAULT now()
);

CREATE TABLE player_attributes (
  player_id uuid PRIMARY KEY REFERENCES players(id) ON DELETE CASCADE,
  str integer DEFAULT 1,
  endu integer DEFAULT 1,
  agi integer DEFAULT 1,
  dex integer DEFAULT 1,
  intel integer DEFAULT 1,
  wits integer DEFAULT 1,
  perc integer DEFAULT 1,
  comp integer DEFAULT 1,
  cha integer DEFAULT 1
);

CREATE TABLE professions (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  name text UNIQUE NOT NULL,
  description text
);

CREATE TABLE player_profession (
  player_id uuid REFERENCES players(id) ON DELETE CASCADE,
  profession_id uuid REFERENCES professions(id),
  is_current boolean DEFAULT false,
  since timestamptz DEFAULT now(),
  PRIMARY KEY (player_id, profession_id)
);

CREATE TABLE reputations (
  player_id uuid REFERENCES players(id) ON DELETE CASCADE,
  faction_id uuid REFERENCES factions(id) ON DELETE CASCADE,
  score integer DEFAULT 0,
  PRIMARY KEY (player_id, faction_id)
);

CREATE TABLE item_defs (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  name text NOT NULL,
  class text NOT NULL,        -- weapon|armor|consumable|utility|contraband|currency|key|cosmetic
  subtype text,
  weight numeric(8,3) DEFAULT 0,
  slot text,                  -- head|body|legs|primary|secondary|etc
  illegal boolean DEFAULT false,
  base_stats jsonb DEFAULT '{}'::jsonb,
  description text
);

CREATE TABLE item_instances (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  item_def_id uuid REFERENCES item_defs(id) ON DELETE CASCADE,
  owner_player_id uuid REFERENCES players(id) ON DELETE SET NULL,
  mint_index integer,
  rarity_seed integer,
  float_title text,
  roll_grade text,
  signature_rune text,
  hidden_trait text,
  condition integer DEFAULT 100,   -- 0..100
  insured boolean DEFAULT false,
  created_at timestamptz DEFAULT now()
);

CREATE TABLE inventory_items (
  player_id uuid REFERENCES players(id) ON DELETE CASCADE,
  item_instance_id uuid REFERENCES item_instances(id) ON DELETE CASCADE,
  location text NOT NULL DEFAULT 'carried',   -- carried|stash|equipped
  slot text,
  PRIMARY KEY (player_id, item_instance_id)
);

CREATE TABLE combats (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  district_id uuid REFERENCES districts(id),
  initiator_player_id uuid REFERENCES players(id),
  defender_player_id uuid REFERENCES players(id),
  initiator_online boolean DEFAULT true,
  defender_online boolean DEFAULT true,
  outcome text,
  started_at timestamptz DEFAULT now(),
  ended_at timestamptz
);

CREATE TABLE range_state (
  combat_id uuid PRIMARY KEY REFERENCES combats(id) ON DELETE CASCADE,
  current_range text NOT NULL,   -- Close|Near|Mid|Far|OutOfRange
  round_number integer DEFAULT 1
);

CREATE TABLE combat_participants (
  combat_id uuid REFERENCES combats(id) ON DELETE CASCADE,
  player_id uuid REFERENCES players(id) ON DELETE CASCADE,
  is_ai boolean DEFAULT false,
  snapshot_stats jsonb DEFAULT '{}'::jsonb,
  PRIMARY KEY (combat_id, player_id)
);

CREATE TABLE combat_turns (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  combat_id uuid REFERENCES combats(id) ON DELETE CASCADE,
  actor_player_id uuid REFERENCES players(id),
  action_type text NOT NULL,       -- melee|ranged|advance|retreat|sprint|block|dodge|use_item|disengage|grapple|suppress|swap
  params jsonb DEFAULT '{}'::jsonb,
  result jsonb DEFAULT '{}'::jsonb,
  created_at timestamptz DEFAULT now()
);

CREATE TABLE status_effect_defs (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  name text UNIQUE NOT NULL,
  description text,
  base_duration integer DEFAULT 1,
  stacking_rule text,      -- none|stack|refresh
  effect_type text         -- bleed|stun|suppression|adrenaline|concealment
);

CREATE TABLE status_effects (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  combat_id uuid REFERENCES combats(id) ON DELETE CASCADE,
  target_player_id uuid REFERENCES players(id) ON DELETE CASCADE,
  status_def_id uuid REFERENCES status_effect_defs(id) ON DELETE CASCADE,
  remaining_turns integer DEFAULT 1,
  potency integer DEFAULT 1,
  created_at timestamptz DEFAULT now()
);

CREATE TABLE heat_events (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  player_id uuid REFERENCES players(id) ON DELETE CASCADE,
  delta integer NOT NULL,
  reason text,
  created_at timestamptz DEFAULT now()
);

CREATE TABLE audit_logs (
  id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  actor_player_id uuid REFERENCES players(id),
  action text NOT NULL,
  payload jsonb DEFAULT '{}'::jsonb,
  created_at timestamptz DEFAULT now()
);

-- Helpful indexes
CREATE INDEX idx_item_instances_owner ON item_instances(owner_player_id);
CREATE INDEX idx_inventory_location ON inventory_items(player_id, location);
CREATE INDEX idx_combat_turns_combat ON combat_turns(combat_id, created_at);
CREATE INDEX idx_status_target ON status_effects(target_player_id);
