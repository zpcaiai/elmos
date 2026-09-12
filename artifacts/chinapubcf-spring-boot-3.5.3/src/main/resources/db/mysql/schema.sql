CREATE TABLE IF NOT EXISTS book (
  book_id BIGINT NOT NULL AUTO_INCREMENT,
  original_name VARCHAR(255),
  author VARCHAR(255),
  name VARCHAR(255) NOT NULL,
  translator VARCHAR(255),
  press VARCHAR(255),
  series_name VARCHAR(255),
  isbn VARCHAR(32),
  press_time VARCHAR(64),
  version VARCHAR(64),
  shelf_time VARCHAR(64),
  category VARCHAR(128),
  price DECIMAL(12,2) NOT NULL DEFAULT 0,
  vip_price DECIMAL(12,2) NOT NULL DEFAULT 0,
  school_price DECIMAL(12,2) NOT NULL DEFAULT 0,
  activity VARCHAR(255),
  sales INT NOT NULL DEFAULT 0,
  PRIMARY KEY (book_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS app_user (
  user_id BIGINT NOT NULL AUTO_INCREMENT,
  name VARCHAR(64) NOT NULL,
  email VARCHAR(255) NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  status VARCHAR(64),
  admire_field VARCHAR(512),
  expert_at VARCHAR(512),
  tag VARCHAR(512),
  know_from VARCHAR(128),
  PRIMARY KEY (user_id),
  UNIQUE KEY uq_app_user_name (name),
  UNIQUE KEY uq_app_user_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS rating (
  rating_id BIGINT NOT NULL AUTO_INCREMENT,
  user_id BIGINT NOT NULL,
  book_id BIGINT NOT NULL,
  rating DECIMAL(3,2) NOT NULL,
  rated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (rating_id),
  UNIQUE KEY uq_rating_user_book (user_id, book_id),
  KEY idx_rating_user (user_id),
  KEY idx_rating_book (book_id),
  CONSTRAINT ck_rating_range CHECK (rating >= 1 AND rating <= 5),
  CONSTRAINT fk_rating_user FOREIGN KEY (user_id) REFERENCES app_user(user_id),
  CONSTRAINT fk_rating_book FOREIGN KEY (book_id) REFERENCES book(book_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

