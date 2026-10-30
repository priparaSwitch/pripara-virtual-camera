// Isolated test receiver. Only channels 50/51 are accepted, never cameras 0/1.
// Calls the original UnityCapture SharedImageMemory::Receive unchanged.
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <stdint.h>
#include <atomic>
#include <cstring>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <vector>
#define private public
#include "../native/upper/shared.inl"
#undef private

namespace {
struct Receiver {
    int channel;
    std::unique_ptr<SharedImageMemory> memory;
    std::atomic<bool> stopping{false};
    std::mutex lock;
    std::thread thread;
    std::vector<uint8_t> pixels;
    int32_t header[8]{};
    uint64_t sequence=0;
    HANDLE claim=nullptr;
    explicit Receiver(int c):channel(c) {}
    static void receive(int w,int h,int stride,SharedImageMemory::EFormat format,
                        SharedImageMemory::EResizeMode resize,
                        SharedImageMemory::EMirrorMode mirror,int timeout,
                        uint8_t* data,void* context) {
        auto* self=static_cast<Receiver*>(context);
        if(w<1 || h<1 || w>3840 || h>2160 || stride<w || stride>3840 || format!=0)
            return;
        std::lock_guard<std::mutex> guard(self->lock);
        self->header[0]=MAX_SHARED_IMAGE_SIZE;
        self->header[1]=w; self->header[2]=h; self->header[3]=stride;
        self->header[4]=format; self->header[5]=resize;
        self->header[6]=mirror; self->header[7]=timeout;
        self->pixels.assign(data,data+size_t(stride)*h*4);
        ++self->sequence;
    }
    bool start() {
        std::wstring name=L"UnityCapture_Mutx";
        name.push_back(wchar_t(L'0'+channel));
        claim=CreateMutexW(nullptr,FALSE,name.c_str());
        if(!claim || GetLastError()==ERROR_ALREADY_EXISTS) {
            if(claim) CloseHandle(claim);
            claim=nullptr; return false;
        }
        resume();
        return true;
    }
    void resume() {
        if(thread.joinable()) return;
        memory=std::make_unique<SharedImageMemory>(channel);
        stopping=false;
        thread=std::thread([this] {
            while(!stopping) {
                memory->Receive(&Receiver::receive,this);
                Sleep(1);
            }
        });
    }
    void pause() {
        stopping=true;
        if(thread.joinable()) thread.join();
        // Original class closes handles but does not unmap. Only this fixture
        // adds cleanup; Receive, published names and header remain untouched.
        if(memory && memory->m_pSharedBuf) {
            UnmapViewOfFile(memory->m_pSharedBuf); memory->m_pSharedBuf=nullptr;
        }
        memory.reset();
        std::lock_guard<std::mutex> guard(lock);
        pixels.clear(); sequence=0;
    }
    ~Receiver() {
        pause();
        if(claim) CloseHandle(claim);
    }
};
}
#define API extern "C" __declspec(dllexport)
API void* __cdecl PPFT_Start(int channel) {
    if(channel!=50 && channel!=51) return nullptr;
    auto* receiver=new Receiver(channel);
    if(!receiver->start()) { delete receiver; return nullptr; }
    return receiver;
}
API int __cdecl PPFT_Frame(void* handle,uint8_t* pixels,uint64_t size,
                           int32_t* header,uint64_t* sequence) {
    if(!handle || !header || !sequence) return -1;
    auto* receiver=static_cast<Receiver*>(handle);
    std::lock_guard<std::mutex> guard(receiver->lock);
    *sequence=receiver->sequence;
    if(!receiver->sequence) return 0;
    if(!pixels || size<receiver->pixels.size()) return -1;
    std::memcpy(header,receiver->header,sizeof(receiver->header));
    std::memcpy(pixels,receiver->pixels.data(),receiver->pixels.size());
    return int(receiver->pixels.size());
}
API void __cdecl PPFT_Stop(void* handle) { delete static_cast<Receiver*>(handle); }
API void __cdecl PPFT_Pause(void* handle) {
    if(handle) static_cast<Receiver*>(handle)->pause();
}
API void __cdecl PPFT_Resume(void* handle) {
    if(handle) static_cast<Receiver*>(handle)->resume();
}
