import { IsInt, IsNumber, IsObject, IsOptional, Max, Min } from 'class-validator';
import { Type } from 'class-transformer';

export class CreateSessionDto {
  @Type(() => Number)
  @IsInt()
  @Min(1)
  courseId!: number;

  @IsNumber()
  @Min(0)
  @Max(100)
  score!: number;

  // 训练时长上限 24h（Int 列上限内，防误传时间戳）
  @IsInt()
  @Min(0)
  @Max(86_400_000)
  durationMs!: number;

  // 报告：阶段覆盖、平均匹配度等（自由结构）
  @IsOptional()
  @IsObject()
  report?: Record<string, unknown>;
}
