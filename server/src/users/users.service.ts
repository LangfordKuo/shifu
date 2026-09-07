import { BadRequestException, Injectable, NotFoundException } from '@nestjs/common';
import * as bcrypt from 'bcryptjs';
import { PrismaService } from '../prisma/prisma.service';
import { CreateUserDto, QueryUsersDto, UpdateUserDto } from './dto/users.dto';
import { ROLE, USER_STATUS } from '../common/constants';

@Injectable()
export class UsersService {
  constructor(private prisma: PrismaService) {}

  async findAll(query: QueryUsersDto) {
    const page = query.page ?? 1;
    const pageSize = query.pageSize ?? 10;
    const where = query.keyword
      ? {
          OR: [
            { username: { contains: query.keyword } },
            { nickname: { contains: query.keyword } },
          ],
        }
      : {};

    const [items, total] = await this.prisma.$transaction([
      this.prisma.user.findMany({
        where,
        orderBy: { id: 'desc' },
        skip: (page - 1) * pageSize,
        take: pageSize,
        select: {
          id: true,
          username: true,
          nickname: true,
          role: true,
          status: true,
          createdAt: true,
          updatedAt: true,
        },
      }),
      this.prisma.user.count({ where }),
    ]);

    return { items, total, page, pageSize };
  }

  async create(dto: CreateUserDto) {
    const exists = await this.prisma.user.findUnique({
      where: { username: dto.username },
    });
    if (exists) {
      throw new BadRequestException('用户名已存在');
    }
    const user = await this.prisma.user.create({
      data: {
        username: dto.username,
        passwordHash: bcrypt.hashSync(dto.password, 10),
        nickname: dto.nickname ?? dto.username,
        role: dto.role,
      },
      select: {
        id: true,
        username: true,
        nickname: true,
        role: true,
        status: true,
        createdAt: true,
      },
    });
    return user;
  }

  async update(id: number, dto: UpdateUserDto, operatorId: number) {
    const user = await this.prisma.user.findUnique({ where: { id } });
    if (!user) throw new NotFoundException('用户不存在');

    // 不允许管理员通过编辑把自己降级/禁用，避免锁死系统
    if (id === operatorId && (dto.role === ROLE.USER || dto.status === USER_STATUS.DISABLED)) {
      throw new BadRequestException('不能修改自己的角色或禁用自己');
    }
    // 系统内至少保留一名管理员
    if (
      user.role === ROLE.ADMIN &&
      dto.role === ROLE.USER
    ) {
      const adminCount = await this.prisma.user.count({ where: { role: ROLE.ADMIN, status: USER_STATUS.ACTIVE } });
      if (adminCount <= 1) throw new BadRequestException('系统至少需要保留一名管理员');
    }

    const data: Record<string, unknown> = {};
    if (dto.nickname !== undefined) data.nickname = dto.nickname;
    if (dto.role !== undefined) data.role = dto.role;
    if (dto.status !== undefined) data.status = dto.status;
    if (dto.password !== undefined) {
      data.passwordHash = bcrypt.hashSync(dto.password, 10);
      // 重置密码后吊销该用户全部刷新令牌
      await this.prisma.refreshToken.updateMany({
        where: { userId: id, revokedAt: null },
        data: { revokedAt: new Date() },
      });
    }

    return this.prisma.user.update({
      where: { id },
      data,
      select: {
        id: true,
        username: true,
        nickname: true,
        role: true,
        status: true,
        updatedAt: true,
      },
    });
  }

  async remove(id: number, operatorId: number) {
    if (id === operatorId) {
      throw new BadRequestException('不能删除自己');
    }
    const user = await this.prisma.user.findUnique({ where: { id } });
    if (!user) throw new NotFoundException('用户不存在');
    if (user.role === ROLE.ADMIN) {
      const adminCount = await this.prisma.user.count({ where: { role: ROLE.ADMIN } });
      if (adminCount <= 1) throw new BadRequestException('系统至少需要保留一名管理员');
    }
    await this.prisma.user.delete({ where: { id } });
    return { success: true };
  }
}
