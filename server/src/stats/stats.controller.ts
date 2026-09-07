import { Controller, Get } from '@nestjs/common';
import { PrismaService } from '../prisma/prisma.service';
import { Roles } from '../common/decorators/roles.decorator';
import { ROLE, COURSE_STATUS } from '../common/constants';

@Controller('admin/stats')
@Roles(ROLE.ADMIN)
export class StatsController {
  constructor(private prisma: PrismaService) {}

  @Get()
  async stats() {
    const [users, courses, published, sessionsAgg, recent, byCourse] =
      await Promise.all([
        this.prisma.user.count(),
        this.prisma.course.count(),
        this.prisma.course.count({ where: { status: COURSE_STATUS.PUBLISHED } }),
        this.prisma.trainingSession.aggregate({
          _count: true,
          _avg: { score: true },
        }),
        this.prisma.trainingSession.findMany({
          orderBy: { id: 'desc' },
          take: 8,
          include: {
            user: { select: { nickname: true, username: true } },
            course: { select: { title: true } },
          },
        }),
        this.prisma.trainingSession.groupBy({
          by: ['courseId'],
          _count: true,
          _avg: { score: true },
        }),
      ]);

    const courseIds = byCourse.map((b) => b.courseId);
    const coursesInfo = await this.prisma.course.findMany({
      where: { id: { in: courseIds } },
      select: { id: true, title: true },
    });
    const titleMap = new Map(coursesInfo.map((c) => [c.id, c.title]));

    return {
      users,
      courses,
      published,
      sessions: sessionsAgg._count,
      avgScore: sessionsAgg._avg.score ? Number(sessionsAgg._avg.score.toFixed(1)) : null,
      recent: recent.map((s) => ({
        id: s.id,
        user: s.user.nickname ?? s.user.username,
        course: s.course.title,
        score: s.score,
        durationMs: s.durationMs,
        createdAt: s.createdAt,
      })),
      courseScores: byCourse
        .map((b) => ({
          courseId: b.courseId,
          title: titleMap.get(b.courseId) ?? '—',
          sessions: b._count,
          avgScore: b._avg.score ? Number(b._avg.score.toFixed(1)) : null,
        }))
        .sort((a, b) => b.sessions - a.sessions),
    };
  }
}
