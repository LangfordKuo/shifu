import { Body, Controller, Get, Post, Req } from '@nestjs/common';
import { PrismaService } from '../prisma/prisma.service';
import { CreateSessionDto } from './dto/training.dto';

@Controller('training')
export class TrainingController {
  constructor(private prisma: PrismaService) {}

  /** 记录一次训练会话（课程训练结束时由前端上报） */
  @Post('sessions')
  createSession(
    @Req() req: { user: { id: number } },
    @Body() dto: CreateSessionDto,
  ) {
    return this.prisma.trainingSession.create({
      data: {
        userId: req.user.id,
        courseId: dto.courseId,
        score: dto.score,
        durationMs: dto.durationMs,
        reportJson: dto.report ? JSON.stringify(dto.report) : null,
      },
    });
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
