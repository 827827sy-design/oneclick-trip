CREATE TABLE IF NOT EXISTS ai_user_travel_preferences (
  user_id VARCHAR(128) PRIMARY KEY,
  preference_json JSON NOT NULL,
  source_version INT NOT NULL DEFAULT 0,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ai_travel_plan_versions (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  user_id VARCHAR(128) NOT NULL,
  conversation_id VARCHAR(128) NOT NULL,
  plan_id VARCHAR(128) NOT NULL,
  plan_version INT NOT NULL,
  destination VARCHAR(128) NOT NULL,
  plan_json JSON NOT NULL,
  is_current TINYINT(1) NOT NULL DEFAULT 1,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_ai_plan_version (user_id, conversation_id, plan_id, plan_version),
  KEY idx_ai_plan_current (user_id, conversation_id, is_current),
  KEY idx_ai_plan_created (user_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS ai_booking_draft (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  draft_id VARCHAR(128) NOT NULL,
  user_id VARCHAR(128) NOT NULL,
  conversation_id VARCHAR(128) NOT NULL,
  plan_id VARCHAR(128) NOT NULL,
  plan_version INT NOT NULL,
  booking_types_json JSON NOT NULL,
  selected_option_ids_json JSON NOT NULL,
  status VARCHAR(32) NOT NULL,
  confirmation_token_hash CHAR(64) NOT NULL,
  idempotency_key VARCHAR(128) NULL,
  expires_at DATETIME NOT NULL,
  confirmed_at DATETIME NULL,
  create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_ai_booking_draft_id (draft_id),
  UNIQUE KEY uk_ai_booking_idempotency (idempotency_key),
  KEY idx_ai_booking_user_status (user_id, status, create_time),
  KEY idx_ai_booking_plan (user_id, conversation_id, plan_id, plan_version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
