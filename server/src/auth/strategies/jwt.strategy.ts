import { Injectable, UnauthorizedException } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { PassportStrategy } from '@nestjs/passport';
import { ExtractJwt, Strategy } from 'passport-jwt';
import { PrismaService } from '../../prisma/prisma.service';

interface JwtPayload {
  sub: string;
  username: string;
  role: string;
}

@Injectable()
export class JwtStrategy extends PassportStrategy(Strategy) {
  constructor(
    private prisma: PrismaService,
    configService: ConfigService,
  ) {
    super({
      jwtFromRequest: ExtractJwt.fromAuthHeaderAsBearerToken(),
      ignoreExpiration: false,
      secretOrKey: configService.getOrThrow<string>('JWT_SECRET'),
    });
  }

  /** 每次请求校验：用户仍存在且未被禁用 */
  async validate(payload: JwtPayload) {
    const user = await this.prisma.user.findUnique({
      where: { id: Number(payload.sub) },
    });
    if (!user || user.status !== 'ACTIVE') {
      throw new UnauthorizedException('账号不可用');
    }
    return user;
  }
}
