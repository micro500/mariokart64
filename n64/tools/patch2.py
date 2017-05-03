#!/usr/bin/env python3
import struct
import sys

class Patcher:
    PATCH_TYPE_BYTES = 0
    PATCH_TYPE_JUMP  = 1
    PATCH_TYPE_JAL   = 2
    PATCH_TYPE_PTR   = 3
    patchTypes = ['bytes', 'jump', 'jal', 'ptr']

    def __init__(self):
        self.patches  = []
        self.sections = {}
        self.symbols  = {}


    def bytes2int(self, b):
        return struct.unpack_from('>I', b)[0]


    def _makeJump(self, addr, mask):
        return (((addr & 0xFFFFFF) >> 2) | mask).to_bytes(4, 'big')


    def makeJump(self, addr):
        """Given `addr`, return the opcode for `J addr`."""
        return self._makeJump(addr, 0x08000000)


    def makeJAL(self, addr):
        """Given `addr`, return the opcode for `JAL addr`."""
        return self._makeJump(addr, 0x0C000000)


    def readSections(self, src):
        """Read sections list, as generated by:
        mips64-elf-objdump -hw file.elf
        """
        with open(src) as file:
            while True:
                line = file.readline()
                if line == '': break
                parts = line.strip().split()
                try: int(parts[0])
                except (ValueError, IndexError): continue
                sec = dict(
                    name   = parts[1],
                    size   = int(parts[2], 16),
                    vma    = int(parts[3], 16),
                    lma    = int(parts[4], 16),
                    offset = int(parts[5], 16),
                )
                self.sections[sec['name']] = sec


    def readSymbols(self, path):
        """Read symbols.txt"""
        with open(path) as listFile:
            while True:
                line = listFile.readline()
                if line == '': break # end of file

                line = line.split()
                if len(line) < 4: continue

                address = int(line[0], base=16) & 0xFFFFFFFF
                size    = int(line[1], base=16)
                symbol  = dict(
                    address = address,
                    name    = line[3],
                    size    = size,
                )
                self.symbols[address] = symbol


    def readPatches(self, listPath, binPath):
        """Read patches.txt"""
        self.binFile = open(binPath, 'rb')

        startAddr = None
        with open(listPath) as listFile:
            while True:
                line = listFile.readline()
                if line == '': break # end of file

                # nm gives us memory addresses, we need to convert those
                # to section-relative offsets
                address = int(line.split()[0], base=16)
                if startAddr is None: startAddr = address
                self.patches.append(address - startAddr)

        # add the end of the binFile as the last offset
        self.binFile.seek(0, 2)
        binSize = self.binFile.tell()
        self.patches.append(binSize)


    def applyPatchPtr(self, patchOffs, data, target, elf):
        address = self.bytes2int(data)
        symbol  = self.symbols[address]
        offset  = address - self.sections['.text']['vma'] # XXX lma?
        if offset < 0:
            raise ValueError(
                "Symbol %s is not in .text section" % symbol['name'])
        offset += self.sections['.text']['offset']

        print("ptr: symbol %s at 0x%X => 0x%X, size 0x%X, target 0x%X" % (
            symbol['name'], address, offset, symbol['size'], patchOffs ))
        elf.seek(offset, 0)
        data = elf.read(symbol['size'])
        target.seek(patchOffs)
        target.write(data)


    def applyPatch(self, idx, target, elf):
        startOffs, endOffs = self.patches[idx], self.patches[idx+1]
        size = endOffs - startOffs

        # read patch data
        self.binFile.seek(startOffs, 0)
        data = self.binFile.read(size)
        offset, patchType = struct.unpack_from('>II', data)
        data = data[8:]
        print("patch: %-5s at 0x%08X => %s" % (
            self.patchTypes[patchType], offset, data.hex()))

        target.seek(offset, 0)
        if patchType == self.PATCH_TYPE_BYTES:
            target.write(data)
        elif patchType == self.PATCH_TYPE_JUMP:
            target.write(self.makeJump(self.bytes2int(data)))
        elif patchType == self.PATCH_TYPE_JAL:
            target.write(self.makeJAL(self.bytes2int(data)))
        elif patchType == self.PATCH_TYPE_PTR:
            self.applyPatchPtr(offset, data, target, elf)
        else:
            raise ValueError("Unknown patch type: " + str(patchType))


    def applyPatches(self, target, elf):
        for i in range(len(self.patches) - 1):
            self.applyPatch(i, target, elf)


def main(targetPath, patchPath, elfPath):
    print("patch " + str(targetPath) + " with " + str(patchPath))
    p = Patcher()
    p.readPatches (patchPath + '/patches.txt', patchPath + '/patches.bin')
    p.readSections(patchPath + '/sections.txt')
    p.readSymbols (patchPath + '/symbols.txt')
    with open(targetPath, 'r+b') as target:
        with open(elfPath, 'rb') as elf:
            p.applyPatches(target, elf)
    return 0


if __name__ == '__main__':
    sys.exit(main(*sys.argv[1:]))
