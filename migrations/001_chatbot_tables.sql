-- Run this on EVERY tenant database (each university's own `db_name`),
-- and add it to whatever script/template you use to provision a new
-- university's database, so new tenants get it automatically.
--
-- `chatbot_faqs`, `chatbot_logs` and `chatbot_learning` already exist in
-- the base schema (databases.sql) and are reused as-is.

-- 1) Institute documents used for retrieval-augmented answers
--    (reglement interieur, procedures, guides, admin-uploaded PDFs/text...)
CREATE TABLE IF NOT EXISTS `chatbot_documents` (
  `id` INT(11) NOT NULL AUTO_INCREMENT,
  `title` VARCHAR(255) NOT NULL,
  `uploaded_by` INT(11) DEFAULT NULL COMMENT 'university/admin id who uploaded it',
  `created_at` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `chatbot_document_chunks` (
  `id` INT(11) NOT NULL AUTO_INCREMENT,
  `document_id` INT(11) NOT NULL,
  `chunk_index` INT(11) NOT NULL,
  `chunk_text` TEXT NOT NULL,
  PRIMARY KEY (`id`),
  KEY `document_id` (`document_id`),
  CONSTRAINT `chatbot_document_chunks_ibfk_1`
    FOREIGN KEY (`document_id`) REFERENCES `chatbot_documents` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2) Announcements posted by the administration
CREATE TABLE IF NOT EXISTS `announcements` (
  `id` INT(11) NOT NULL AUTO_INCREMENT,
  `title` VARCHAR(255) NOT NULL,
  `content` TEXT NOT NULL,
  `audience` ENUM('all','students','teachers') NOT NULL DEFAULT 'all',
  `is_active` TINYINT(1) NOT NULL DEFAULT 1,
  `created_at` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_audience_active` (`audience`, `is_active`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 3) Make sure chatbot_faqs.lang has a sane default (older rows may be NULL)
UPDATE `chatbot_faqs` SET `lang` = 'fr' WHERE `lang` IS NULL;
