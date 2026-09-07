import { Module } from '@nestjs/common';
import { AiConfigController } from './aiconfig.controller';
import { AiConfigService } from './aiconfig.service';

@Module({
  controllers: [AiConfigController],
  providers: [AiConfigService],
  exports: [AiConfigService],
})
export class AiConfigModule {}
