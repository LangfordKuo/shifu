import { SetMetadata } from '@nestjs/common';

export const ROLES_KEY = 'shifu:roles';
/** 声明允许访问的角色，如 @Roles(ROLE.ADMIN, ROLE.USER) */
export const Roles = (...roles: string[]) => SetMetadata(ROLES_KEY, roles);
