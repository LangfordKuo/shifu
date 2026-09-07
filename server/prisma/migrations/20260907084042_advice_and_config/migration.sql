-- AlterTable
ALTER TABLE "TrainingSession" ADD COLUMN "advice" TEXT;

-- CreateTable
CREATE TABLE "SystemConfig" (
    "key" TEXT NOT NULL PRIMARY KEY,
    "value" TEXT NOT NULL,
    "updatedAt" DATETIME NOT NULL
);
