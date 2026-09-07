import { Module } from '@nestjs/common';
import { InternalController } from './internal.controller';
import { CoursesModule } from '../courses/courses.module';

@Module({
  imports: [CoursesModule],
  controllers: [InternalController],
})
export class InternalModule {}
