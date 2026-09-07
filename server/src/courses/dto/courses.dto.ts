import { IsIn, IsOptional, IsString, MaxLength, MinLength } from 'class-validator';

export class CreateCourseDto {
  @IsString()
  @MinLength(2, { message: '课程标题至少 2 个字符' })
  @MaxLength(64)
  title!: string;

  @IsOptional()
  @IsString()
  @MaxLength(500)
  description?: string;

  @IsOptional()
  @IsIn(['general', 'taiji', 'changquan', 'taolu'], { message: '分类不合法' })
  category?: string;
}

export class UpdateCourseDto {
  @IsOptional()
  @IsString()
  @MinLength(2)
  @MaxLength(64)
  title?: string;

  @IsOptional()
  @IsString()
  @MaxLength(500)
  description?: string;

  @IsOptional()
  @IsIn(['DRAFT', 'PUBLISHED', 'OFFLINE'], { message: '状态不合法' })
  status?: string;
}
