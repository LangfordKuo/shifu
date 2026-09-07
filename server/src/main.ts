import 'reflect-metadata';
import { NestFactory } from '@nestjs/core';
import { ValidationPipe } from '@nestjs/common';
import * as express from 'express';
import * as path from 'node:path';
import { AppModule } from './app.module';

async function bootstrap() {
  const app = await NestFactory.create(AppModule);
  app.setGlobalPrefix('api');
  app.useGlobalPipes(
    new ValidationPipe({ whitelist: true, transform: true }),
  );
  app.enableCors({ origin: true, credentials: true });

  // 静态资源：上传的视频 / 课程封面（/api/uploads/...）
  const uploadDir = path.resolve(
    process.cwd(),
    process.env.UPLOAD_DIR ?? 'uploads',
  );
  app.use('/api/uploads', express.static(uploadDir));

  const port = Number(process.env.PORT ?? 3000);
  await app.listen(port);
  console.log(`[shifu-server] http://localhost:${port}/api`);
}

void bootstrap();
