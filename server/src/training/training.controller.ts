import { Body, Controller, Get, Post, Req } from '@nestjs/common';
import { PrismaService } from '../prisma/prisma.service';
import { AiConfigService } from '../aiconfig/aiconfig.service';
import { CreateSessionDto } from './dto/training.dto';

@Controller('training')
export class TrainingController {
  constructor(
    private prisma: PrismaService,
    private aiConfigService: AiConfigService,
  ) {}

  /** 记录一次训练会话（课程训练结束时由前端上报），并异步生成 AI 训练建议 */
  @Post('sessions')
  async createSession(
    @Req() req: { user: { id: number } },
    @Body() dto: CreateSessionDto,
  ) {
    const session = await this.prisma.trainingSession.create({
      data: {
        userId: req.user.id,
        courseId: dto.courseId,
        score: dto.score,
        durationMs: dto.durationMs,
        reportJson: dto.report ? JSON.stringify(dto.report) : null,
      },
    });
    // DeepSeek 建议在后台生成，不阻塞上报；完成后写入 advice 字段
    void this.aiConfigService.generateAdviceForSession(session.id);
    return session;
  }

  /** 我的训练记录 */
  @Get('sessions/mine')
  mySessions(@Req() req: { user: { id: number } }) {
    return this.prisma.trainingSession.findMany({
      where: { userId: req.user.id },
      orderBy: { id: 'desc' },
      take: 50,
      include: { course: { select: { title: true } } },
    });
  }
}
