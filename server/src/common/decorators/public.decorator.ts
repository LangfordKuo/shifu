import { SetMetadata } from '@nestjs/common';

export const IS_PUBLIC_KEY = 'shifu:isPublic';
/** 跳过 JWT 鉴权（登录/刷新等公开接口） */
export const Public = () => SetMetadata(IS_PUBLIC_KEY, true);
