import {
  BadRequestException,
  Injectable,
  NotFoundException,
} from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import * as fs from 'node:fs';
import * as path from 'node:path';
import { PrismaService } from '../prisma/prisma.service';
import { CreateCourseDto, UpdateCourseDto } from './dto/courses.dto';
import { COURSE_STATUS, JOB_STATUS } from '../common/constants';

@Injectable()
export class CoursesService {
  constructor(
    private prisma: PrismaService,
    private config: ConfigService,
  ) {}

  /** uploads 根目录（与 main.ts 静态目录一致） */
  private uploadRoot() {
    return path.resolve(process.cwd(), this.config.get('UPLOAD_DIR', 'uploads'));
  }

  // ---------- 管理端 ----------

  async create(dto: CreateCourseDto, file: Express.Multer.File, userId: number) {
    const course = await this.prisma.course.create({
      data: {
        title: dto.title,
        description: dto.description,
        category: dto.category ?? 'general',
        videoPath: `/api/uploads/videos/${file.filename}`,
        status: COURSE_STATUS.TRAINING,
        createdById: userId,
      },
    });

    const job = await this.prisma.trainingJob.create({
      data: { courseId: course.id, type: 'EXTRACT', status: JOB_STATUS.RUNNING },
    });

    // 触发 Python 提取关键帧（失败则任务标记 FAILED，可重试）
    try {
      const aiBase = this.config.get('AI_BASE_URL', 'http://localhost:8000');
      const token = this.config.getOrThrow<string>('INTERNAL_TOKEN');
      const resp = await fetch(`${aiBase}/api/extract`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Internal-Token': token,
        },
        body: JSON.stringify({
          job_id: job.id,
          course_id: course.id,
          video_path: path.resolve(this.uploadRoot(), 'videos', file.filename),
          uploads_root: this.uploadRoot(),
        }),
      });
      if (!resp.ok) throw new Error(`AI 服务响应 ${resp.status}`);
    } catch (err) {
      await this.prisma.trainingJob.update({
        where: { id: job.id },
        data: {
          status: JOB_STATUS.FAILED,
          error: `无法调用 AI 服务：${err instanceof Error ? err.message : err}`,
        },
      });
      await this.prisma.course.update({
        where: { id: course.id },
        data: { status: COURSE_STATUS.DRAFT },
      });
    }

    return this.findOneAdmin(course.id);
  }

  async findAllAdmin() {
    const courses = await this.prisma.course.findMany({
      orderBy: { id: 'desc' },
      include: {
        models: { where: { isActive: true }, take: 1 },
        jobs: { orderBy: { id: 'desc' }, take: 1 },
      },
    });
    return {
      items: courses.map((c) => ({
        id: c.id,
        title: c.title,
        description: c.description,
        category: c.category,
        coverUrl: c.coverUrl,
        status: c.status,
        videoPath: c.videoPath,
        createdAt: c.createdAt,
        keyframeCount: c.models[0]?.keyframeCount ?? 0,
        durationMs: c.models[0]?.durationMs ?? 0,
        job: c.jobs[0]
          ? {
              id: c.jobs[0].id,
              type: c.jobs[0].type,
              status: c.jobs[0].status,
              progress: c.jobs[0].progress,
              error: c.jobs[0].error,
            }
          : null,
      })),
    };
  }

  async findOneAdmin(id: number) {
    const c = await this.prisma.course.findUnique({
      where: { id },
      include: {
        models: { where: { isActive: true }, take: 1 },
        jobs: { orderBy: { id: 'desc' }, take: 1 },
      },
    });
    if (!c) throw new NotFoundException('课程不存在');
    return { ...c, job: c.jobs[0] ?? null };
  }

  async update(id: number, dto: UpdateCourseDto) {
    const course = await this.prisma.course.findUnique({ where: { id } });
    if (!course) throw new NotFoundException('课程不存在');

    if (dto.status === COURSE_STATUS.PUBLISHED) {
      const model = await this.prisma.courseModel.findFirst({
        where: { courseId: id, isActive: true },
      });
      if (!model) {
        throw new BadRequestException('课程还没有生成动作模型，无法发布');
      }
    }

    return this.prisma.course.update({
      where: { id },
      data: {
        ...(dto.title !== undefined ? { title: dto.title } : {}),
        ...(dto.description !== undefined ? { description: dto.description } : {}),
        ...(dto.status !== undefined ? { status: dto.status } : {}),
      },
    });
  }

  async remove(id: number) {
    const course = await this.prisma.course.findUnique({ where: { id } });
    if (!course) throw new NotFoundException('课程不存在');
    await this.prisma.course.delete({ where: { id } });
    // 删除视频文件（尽力而为）
    if (course.videoPath?.startsWith('/api/uploads/')) {
      const rel = course.videoPath.replace('/api/uploads/', '');
      fs.promises
        .unlink(path.resolve(this.uploadRoot(), rel))
        .catch(() => {});
    }
    return { success: true };
  }

  /** 任务进度回调（Python → 内部接口），成功时落库课程模型 */
  async applyJobUpdate(
    jobId: number,
    update: {
      status?: string;
      progress?: number;
      error?: string;
      result?: {
        modelPath: string;
        keyframeCount: number;
        durationMs: number;
        coverUrl?: string;
      };
    },
  ) {
    const job = await this.prisma.trainingJob.findUnique({ where: { id: jobId } });
    if (!job) throw new NotFoundException('任务不存在');

    const data: Record<string, unknown> = {};
    if (update.status !== undefined) data.status = update.status;
    if (update.progress !== undefined) data.progress = Math.round(update.progress);
    if (update.error !== undefined) data.error = update.error;

    if (update.status === JOB_STATUS.SUCCESS && update.result) {
      const { modelPath, keyframeCount, durationMs, coverUrl } = update.result;
      await this.prisma.$transaction([
        this.prisma.courseModel.updateMany({
          where: { courseId: job.courseId, isActive: true },
          data: { isActive: false },
        }),
        this.prisma.courseModel.create({
          data: {
            courseId: job.courseId,
            version: 1,
            modelPath,
            keyframeCount,
            durationMs,
            isActive: true,
          },
        }),
        this.prisma.course.update({
          where: { id: job.courseId },
          data: {
            status: COURSE_STATUS.DRAFT,
            ...(coverUrl ? { coverUrl } : {}),
          },
        }),
      ]);
    } else if (update.status === JOB_STATUS.FAILED) {
      await this.prisma.course.update({
        where: { id: job.courseId },
        data: { status: COURSE_STATUS.DRAFT },
      });
    }

    return this.prisma.trainingJob.update({ where: { id: jobId }, data });
  }

  // ---------- 用户端 ----------

  /** 内部接口：返回课程信息 + 激活模型 JSON 内容（供 Python 训练对齐用） */
  async getCourseModelPayload(id: number) {
    const course = await this.prisma.course.findUnique({
      where: { id },
      include: { models: { where: { isActive: true }, take: 1 } },
    });
    const model = course?.models[0];
    if (!course || !model) throw new NotFoundException('课程模型不存在');

    let parsed: unknown;
    try {
      parsed = JSON.parse(await fs.promises.readFile(model.modelPath, 'utf-8'));
    } catch {
      throw new NotFoundException('课程模型文件缺失，请重新提取');
    }
    return {
      course: { id: course.id, title: course.title },
      model: parsed,
    };
  }

  async findAllPublished() {
    const courses = await this.prisma.course.findMany({
      where: { status: COURSE_STATUS.PUBLISHED },
      orderBy: { id: 'desc' },
      include: { models: { where: { isActive: true }, take: 1 } },
    });
    return {
      items: courses.map((c) => ({
        id: c.id,
        title: c.title,
        description: c.description,
        category: c.category,
        coverUrl: c.coverUrl,
        keyframeCount: c.models[0]?.keyframeCount ?? 0,
        durationMs: c.models[0]?.durationMs ?? 0,
      })),
    };
  }

  async findOnePublished(id: number) {
    const c = await this.prisma.course.findFirst({
      where: { id, status: COURSE_STATUS.PUBLISHED },
      include: { models: { where: { isActive: true }, take: 1 } },
    });
    if (!c) throw new NotFoundException('课程不存在或未发布');
    return {
      id: c.id,
      title: c.title,
      description: c.description,
      category: c.category,
      coverUrl: c.coverUrl,
      keyframeCount: c.models[0]?.keyframeCount ?? 0,
      durationMs: c.models[0]?.durationMs ?? 0,
    };
  }
}
