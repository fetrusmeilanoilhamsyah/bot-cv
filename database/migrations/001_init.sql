-- 001_init.sql
-- Jalankan di phpMyAdmin pada database dibotvcf

CREATE TABLE IF NOT EXISTS users (
    id BIGINT PRIMARY KEY,
    username VARCHAR(255),
    full_name VARCHAR(255),
    is_member TINYINT(1) DEFAULT 0,
    joined_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_active DATETIME
);

CREATE TABLE IF NOT EXISTS sessions (
    user_id BIGINT PRIMARY KEY,
    state VARCHAR(100),
    data JSON,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS broadcast_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    admin_id BIGINT,
    message TEXT,
    sent_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    success_count INT DEFAULT 0,
    fail_count INT DEFAULT 0
);
