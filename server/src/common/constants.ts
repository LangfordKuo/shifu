/** 角色常量：SQLite 下存字符串，切 MySQL 后可平滑迁为 enum */
export const ROLE = {
  ADMIN: 'ADMIN',
  USER: 'USER',
} as const;

/** 用户状态 */
export const USER_STATUS = {
  ACTIVE: 'ACTIVE',
  DISABLED: 'DISABLED',
} as const;

/** 课程状态 */
export const COURSE_STATUS = {
  DRAFT: 'DRAFT',
  TRAINING: 'TRAINING',
  PUBLISHED: 'PUBLISHED',
  OFFLINE: 'OFFLINE',
} as const;

/** 任务状态 */
export const JOB_STATUS = {
  PENDING: 'PENDING',
  RUNNING: 'RUNNING',
  SUCCESS: 'SUCCESS',
  FAILED: 'FAILED',
} as const;
