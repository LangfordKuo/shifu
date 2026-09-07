import {
  Body,
  Controller,
  Get,
  Param,
  ParseIntPipe,
  Patch,
  Req,
  UnauthorizedException,
} from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { Type } from 'class-transformer';
import {
  IsIn,
  IsInt,
  IsObject,
  IsOptional,
  IsString,
  Max,
  Min,
  ValidateNested,
} from 'class-validator';
import { CoursesService } from '../courses/courses.service';
import { Public } from '../common/decorators/public.decorator';

class JobResultDto {
  @IsString()
  modelPath!: string;

  @IsInt()
  @Min(0)
  keyframeCount!: number;

  @IsInt()
  @Min(0)
  durationMs!: number;

  @IsOptional()
  @IsString()
  coverUrl?: string;
}

// 注意：全局 ValidationPipe 开启 whitelist，未加装饰器的属性会被剥除，
// 因此每个字段（含嵌套对象）都必须显式声明校验规则。
class UpdateJobDto {
  @IsOptional()
  @IsIn(['RUNNING', 'SUCCESS', 'FAILED'])
  status?: string;

  @IsOptional()
  @IsInt()
  @Min(0)
  @Max(100)
  progress?: number;

  @IsOptional()
  @IsString()
  error?: string;

  @IsOptional()
  @IsObject()
  @ValidateNested()
  @Type(() => JobResultDto)
  result?: JobResultDto;
}

/**
 * 服务间内部接口（Node ← Python）：
 * 任务进度回调 + 课程模型下发。用共享 INTERNAL_TOKEN 鉴权。
 */
@Controller('internal')
export class InternalController {
  constructor(
    private coursesService: CoursesService,
    private config: ConfigService,
  ) {}

  private assertToken(req: {
    headers: Record<string, string | string[] | undefined>;
  }) {
    const token = req.headers['x-internal-token'];
    const expected = this.config.getOrThrow<string>('INTERNAL_TOKEN');
    if (token !== expected) throw new UnauthorizedException('内部令牌无效');
  }

  @Public()
  @Patch('jobs/:id')
  updateJob(
    @Req() req: { headers: Record<string, string | string[] | undefined> },
    @Param('id', ParseIntPipe) id: number,
    @Body() dto: UpdateJobDto,
  ) {
    this.assertToken(req);
    return this.coursesService.applyJobUpdate(id, dto);
  }

  /** Python 训练连接 start_course 时拉取课程模型 JSON */
  @Public()
  @Get('courses/:id/model')
  getCourseModel(
    @Req() req: { headers: Record<string, string | string[] | undefined> },
    @Param('id', ParseIntPipe) id: number,
  ) {
    this.assertToken(req);
    return this.coursesService.getCourseModelPayload(id);
  }
}
