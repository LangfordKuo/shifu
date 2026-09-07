import { IsIn, IsInt, IsOptional, IsString, Max, Min, MinLength } from 'class-validator';
import { Type } from 'class-transformer';

export class CreateUserDto {
  @IsString()
  @MinLength(2, { message: '用户名至少 2 个字符' })
  username!: string;

  @IsString()
  @MinLength(6, { message: '密码至少 6 位' })
  password!: string;

  @IsOptional()
  @IsString()
  nickname?: string;

  @IsIn(['ADMIN', 'USER'], { message: '角色不合法' })
  role!: string;
}

export class UpdateUserDto {
  @IsOptional()
  @IsString()
  nickname?: string;

  @IsOptional()
  @IsIn(['ADMIN', 'USER'], { message: '角色不合法' })
  role?: string;

  @IsOptional()
  @IsIn(['ACTIVE', 'DISABLED'], { message: '状态不合法' })
  status?: string;

  // 管理员重置密码
  @IsOptional()
  @IsString()
  @MinLength(6, { message: '密码至少 6 位' })
  password?: string;
}

export class QueryUsersDto {
  @IsOptional()
  @IsString()
  keyword?: string;

  @IsOptional()
  @Type(() => Number)
  @IsInt()
  @Min(1)
  page?: number = 1;

  @IsOptional()
  @Type(() => Number)
  @IsInt()
  @Min(1)
  @Max(100)
  pageSize?: number = 10;
}
