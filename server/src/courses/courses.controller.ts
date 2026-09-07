import {
  Body,
  Controller,
  Delete,
  Get,
  Param,
  ParseIntPipe,
  Patch,
  Post,
  Put,
  UploadedFile,
  UseInterceptors,
} from '@nestjs/common';
import { FileInterceptor } from '@nestjs/platform-express';
import { diskStorage } from 'multer';
import { extname, resolve } from 'node:path';
import { randomBytes } from 'node:crypto';
import { mkdirSync } from 'node:fs';
import { Type } from 'class-transformer';
import {
  IsArray,
  IsInt,
  IsString,
  MaxLength,
  Min,
  ValidateNested,
} from 'class-validator';
import { CoursesService } from './courses.service';
import { Roles } from '../common/decorators/roles.decorator';
import { Req } from '@nestjs/common';
import { ROLE } from '../common/constants';
import { CreateCourseDto, UpdateCourseDto } from './dto/courses.dto';

class CueItemDto {
  @IsInt()
  @Min(1)
  index!: number;

  @IsString()
  @MaxLength(60)
  cue!: string;
}

class UpdateCuesDto {
  @IsArray()
  @ValidateNested({ each: true })
  @Type(() => CueItemDto)
  cues!: CueItemDto[];
}

const VIDEO_RE = /\.(mp4|mov|avi|mkv|webm)$/i;

function videoStorage() {
  const dest = resolve(process.cwd(), process.env.UPLOAD_DIR ?? 'uploads', 'videos');
  mkdirSync(dest, { recursive: true });
  return diskStorage({
    destination: (_req, _file, cb) => cb(null, dest),
    filename: (_req, file, cb) =>
      cb(null, `${Date.now()}-${randomBytes(6).toString('hex')}${extname(file.originalname)}`),
  });
}

@Controller('courses')
export class CoursesController {
  constructor(private coursesService: CoursesService) {}

  /** 已发布课程列表（学员） */
  @Get()
  findAllPublished() {
    return this.coursesService.findAllPublished();
  }

  @Get(':id')
  findOnePublished(@Param('id', ParseIntPipe) id: number) {
    return this.coursesService.findOnePublished(id);
  }
}

@Controller('admin/courses')
@Roles(ROLE.ADMIN)
export class AdminCoursesController {
  constructor(private coursesService: CoursesService) {}

  @Get()
  findAllAdmin() {
    return this.coursesService.findAllAdmin();
  }

  @Get(':id')
  findOneAdmin(@Param('id', ParseIntPipe) id: number) {
    return this.coursesService.findOneAdmin(id);
  }

  /** 关键帧清单（供口令编辑） */
  @Get(':id/keyframes')
  getKeyframes(@Param('id', ParseIntPipe) id: number) {
    return this.coursesService.getKeyframes(id);
  }

  @Put(':id/keyframes/cues')
  updateCues(
    @Param('id', ParseIntPipe) id: number,
    @Body() dto: UpdateCuesDto,
  ) {
    return this.coursesService.updateCues(id, dto.cues);
  }

  /** 创建课程：上传示范视频并自动触发关键帧提取 */
  @Post()
  @UseInterceptors(
    FileInterceptor('video', {
      storage: videoStorage(),
      limits: { fileSize: 500 * 1024 * 1024 },
      fileFilter: (_req, file, cb) => {
        if (VIDEO_RE.test(file.originalname)) return cb(null, true);
        cb(new Error('仅支持 MP4 / MOV / AVI / MKV / WebM 视频文件'), false);
      },
    }),
  )
  create(
    @Body() dto: CreateCourseDto,
    @UploadedFile() file: Express.Multer.File | undefined,
    @Req() req: { user: { id: number } },
  ) {
    if (!file) {
      // eslint-disable-next-line @typescript-eslint/no-throw-literal
      throw new Error('请上传示范视频');
    }
    return this.coursesService.create(dto, file, req.user.id);
  }

  @Patch(':id')
  update(
    @Param('id', ParseIntPipe) id: number,
    @Body() dto: UpdateCourseDto,
  ) {
    return this.coursesService.update(id, dto);
  }

  @Delete(':id')
  remove(@Param('id', ParseIntPipe) id: number) {
    return this.coursesService.remove(id);
  }
}
