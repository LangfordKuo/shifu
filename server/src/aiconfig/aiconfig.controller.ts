import { Body, Controller, Get, Post, Put } from '@nestjs/common';
import { IsBoolean, IsOptional, IsString, MaxLength } from 'class-validator';
import { AiConfigService } from './aiconfig.service';
import { Roles } from '../common/decorators/roles.decorator';
import { ROLE } from '../common/constants';

class UpdateAiConfigDto {
  @IsOptional()
  @IsString()
  @MaxLength(200)
  baseUrl?: string;

  @IsOptional()
  @IsString()
  @MaxLength(100)
  model?: string;

  // 传空字符串表示保留原密钥；clearKey=true 表示清除
  @IsOptional()
  @IsString()
  @MaxLength(200)
  apiKey?: string;

  @IsOptional()
  @IsBoolean()
  clearKey?: boolean;

  @IsOptional()
  @IsBoolean()
  enabled?: boolean;
}

class TestAiConfigDto {
  @IsOptional()
  @IsString()
  @MaxLength(200)
  apiKey?: string;
}

@Controller('admin/ai-config')
@Roles(ROLE.ADMIN)
export class AiConfigController {
  constructor(private aiConfigService: AiConfigService) {}

  @Get()
  view() {
    return this.aiConfigService.publicView();
  }

  @Put()
  update(@Body() dto: UpdateAiConfigDto) {
    return this.aiConfigService.updateSettings({
      ...dto,
      apiKey: dto.clearKey ? '' : dto.apiKey,
    });
  }

  /** 测试连接（可传入尚未保存的新密钥先行验证） */
  @Post('test')
  async test(@Body() dto: TestAiConfigDto) {
    if (dto.apiKey) {
      await this.aiConfigService.updateSettings({ apiKey: dto.apiKey });
    }
    return this.aiConfigService.testConnection();
  }
}
