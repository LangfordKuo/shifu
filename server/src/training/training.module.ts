import { Module } from '@nestjs/common';
import { TrainingController } from './training.controller';
import { AiConfigModule } from '../aiconfig/aiconfig.module';

@Module({
  imports: [AiConfigModule],
  controllers: [TrainingController],
})
export class TrainingModule {}
