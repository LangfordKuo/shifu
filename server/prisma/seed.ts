import { PrismaClient } from '@prisma/client';
import * as bcrypt from 'bcryptjs';

const prisma = new PrismaClient();

async function main() {
  const admin = await prisma.user.upsert({
    where: { username: 'admin' },
    update: {},
    create: {
      username: 'admin',
      passwordHash: bcrypt.hashSync('admin123', 10),
      nickname: '管理员',
      role: 'ADMIN',
    },
  });

  const demo = await prisma.user.upsert({
    where: { username: 'user1' },
    update: {},
    create: {
      username: 'user1',
      passwordHash: bcrypt.hashSync('123456', 10),
      nickname: '演示学员',
      role: 'USER',
    },
  });

  console.log(`[seed] admin     -> ${admin.username} / admin123`);
  console.log(`[seed] demo user -> ${demo.username} / 123456`);
}

main()
  .catch((e) => {
    console.error(e);
    process.exit(1);
  })
  .finally(() => prisma.$disconnect());
