import { Module } from '@nestjs/common';
import { CoursesController, AdminCoursesController } from './courses.controller';
import { CoursesService } from './courses.service';

@Module({
  controllers: [CoursesController, AdminCoursesController],
  providers: [CoursesService],
  exports: [CoursesService],
})
export class CoursesModule {}
