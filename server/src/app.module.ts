import { Module } from '@nestjs/common';
import { APP_GUARD } from '@nestjs/core';
import { ConfigModule } from '@nestjs/config';
import { PrismaModule } from './prisma/prisma.module';
import { AuthModule } from './auth/auth.module';
import { UsersModule } from './users/users.module';
import { CoursesModule } from './courses/courses.module';
import { InternalModule } from './internal/internal.module';
import { TrainingModule } from './training/training.module';
import { StatsModule } from './stats/stats.module';
import { AiConfigModule } from './aiconfig/aiconfig.module';
import { JwtAuthGuard } from './common/guards/jwt-auth.guard';
import { RolesGuard } from './common/guards/roles.guard';

@Module({
  imports: [
    ConfigModule.forRoot({ isGlobal: true }),
    PrismaModule,
    AuthModule,
    UsersModule,
    CoursesModule,
    InternalModule,
    TrainingModule,
    StatsModule,
    AiConfigModule,
  ],
  providers: [
    // 全局守卫：先鉴权（可用 @Public() 跳过），再校验角色（可用 @Roles() 声明）
    { provide: APP_GUARD, useClass: JwtAuthGuard },
    { provide: APP_GUARD, useClass: RolesGuard },
  ],
})
export class AppModule {}
