// PriPara CPU-frame sender, independently implemented 2026-10-30.
// Wire protocol: schellingb/UnityCapture commit
// 3ed54c325e0ad71afcf4f246c07e5e17b3d7f2d2, Source/shared.inl.
// No pyvirtualcam code or libyuv code is used. See THIRD_PARTY_NOTICES.
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <stdint.h>
#include <cstring>
#include <map>
#include <memory>
#include <mutex>
#include <string>
#include <vector>

namespace {
constexpr uint64_t MAX_RGBA = uint64_t(3840) * 2160 * 4 * 2;
constexpr int MAX_WIDTH = 3840;
constexpr int MAX_HEIGHT = 2160;
enum Result { OK=0, FRAME_SKIP=1, INACTIVE=2, INVALID=-1,
              ALREADY_OPEN=-2, NO_MEMORY=-3, PROTOCOL=-4, BUSY=-5, IO_ERROR=-6 };
// All eight fields are 32-bit. stride is pixels, not bytes. Pixel data is RGBA.
struct Header {
    uint32_t maxSize;
    int32_t width, height, stride, format, resize, mirror, timeout;
};
static_assert(sizeof(Header)==32, "UnityCapture header ABI");

bool allowed_channel(int channel) {
#ifdef PRIPARA_TEST_CHANNELS
    // Test binaries must never connect to either installed camera channel.
    return channel==50 || channel==51;
#else
    return channel==0 || channel==1;
#endif
}
std::wstring object_name(const wchar_t* prefix, int channel) {
    std::wstring name(prefix);
    if(channel) name.push_back(wchar_t(L'0'+channel));
    return name;
}
struct Sender {
    int channel, width, height, timeout;
    HANDLE mutex=nullptr, want=nullptr, sent=nullptr, mapping=nullptr;
    Header* view=nullptr;
    std::vector<uint8_t> rgba;
    std::mutex lock;
    Sender(int c,int w,int h,int t):channel(c),width(w),height(h),timeout(t),
        rgba(size_t(w)*h*4) {}
    ~Sender() { disconnect(); }
    void disconnect() {
        if(view) { UnmapViewOfFile(view); view=nullptr; }
        for(HANDLE* h : {&mapping,&sent,&want,&mutex}) {
            if(*h) { CloseHandle(*h); *h=nullptr; }
        }
    }
    bool connect() {
        if(view) return true;
        // Explicit MODIFY_STATE permits ReleaseMutex; every wait is bounded.
        if(!mutex) mutex=OpenMutexW(SYNCHRONIZE|MUTEX_MODIFY_STATE,FALSE,
                                   object_name(L"UnityCapture_Mutx",channel).c_str());
        if(!mutex) return false;
        if(!want) want=CreateEventW(nullptr,FALSE,FALSE,
                                   object_name(L"UnityCapture_Want",channel).c_str());
        if(!sent) sent=OpenEventW(EVENT_MODIFY_STATE,FALSE,
                                object_name(L"UnityCapture_Sent",channel).c_str());
        if(!mapping) mapping=OpenFileMappingW(FILE_MAP_WRITE,FALSE,
                              object_name(L"UnityCapture_Data",channel).c_str());
        // Keep the Want event while a receiver finishes its own Open() call.
        // Tearing it down on every inactive frame can miss a periodic receiver.
        if(!want || !sent || !mapping) return false;
        view=static_cast<Header*>(MapViewOfFile(mapping,FILE_MAP_WRITE,0,0,0));
        if(!view) { disconnect(); return false; }
        return true;
    }
    int send(const uint8_t* rgb,uint64_t length,int32_t stride) {
        std::lock_guard<std::mutex> guard(lock);
        if(!rgb || stride<width*3) return INVALID;
        const uint64_t needed=uint64_t(stride)*(height-1)+uint64_t(width)*3;
        if(length!=needed) return INVALID;
        // DirectShow RGB DIBs are bottom-up. UnityCapture keeps row order when
        // turning RGBA into bottom-up BGR; its YUY2 branch flips that BGR back.
        for(int y=0;y<height;++y) {
            const uint8_t* source=rgb+uint64_t(height-1-y)*stride;
            uint8_t* target=rgba.data()+size_t(y)*width*4;
            for(int x=0;x<width;++x) {
                target[4*x]=source[3*x];
                target[4*x+1]=source[3*x+1];
                target[4*x+2]=source[3*x+2];
                target[4*x+3]=255;
            }
        }
        if(!connect()) return INACTIVE;
        DWORD acquired=WaitForSingleObject(mutex,1000);
        if(acquired!=WAIT_OBJECT_0 && acquired!=WAIT_ABANDONED) {
            if(acquired==WAIT_FAILED) disconnect();
            return acquired==WAIT_TIMEOUT ? BUSY : IO_ERROR;
        }
        int result=OK;
        MEMORY_BASIC_INFORMATION region{};
        const bool mapped=VirtualQuery(view,&region,sizeof(region))==sizeof(region);
        const uint64_t room=mapped ? uint64_t(region.RegionSize) : 0;
        if(!mapped || view->maxSize<rgba.size() || view->maxSize>MAX_RGBA ||
           room<sizeof(Header)+rgba.size()) result=PROTOCOL;
        else {
            view->width=width; view->height=height; view->stride=width;
            view->format=0; view->resize=0; view->mirror=0; view->timeout=timeout;
            std::memcpy(reinterpret_cast<uint8_t*>(view)+sizeof(Header),
                        rgba.data(),rgba.size());
        }
        if(!ReleaseMutex(mutex)) return IO_ERROR;
        if(result!=OK) return result;
        if(!SetEvent(sent)) { disconnect(); return IO_ERROR; }
        return WaitForSingleObject(want,0)==WAIT_OBJECT_0 ? OK : FRAME_SKIP;
    }
};
std::mutex registry_lock;
std::map<uint64_t,std::shared_ptr<Sender>> senders;
uint64_t next_id=1;
}

#define API extern "C" __declspec(dllexport)
API uint32_t __cdecl PPF_Version() { return 0x00010000; }
API int32_t __cdecl PPF_Create(int32_t channel,int32_t width,int32_t height,
                              int32_t timeout,uint64_t* handle) {
    if(!handle) return INVALID;
    *handle=0;
    if(!allowed_channel(channel) || width<1 || height<1 ||
       width>MAX_WIDTH || height>MAX_HEIGHT || timeout<0 || timeout>60000)
        return INVALID;
    std::lock_guard<std::mutex> guard(registry_lock);
    for(const auto& item:senders) if(item.second->channel==channel) return ALREADY_OPEN;
    try {
        auto sender=std::make_shared<Sender>(channel,width,height,timeout);
        uint64_t id=next_id++;
        if(!id) id=next_id++;
        senders.emplace(id,std::move(sender)); *handle=id; return OK;
    } catch(...) { return NO_MEMORY; }
}
API int32_t __cdecl PPF_SendRgb(uint64_t handle,const uint8_t* rgb,
                               uint64_t length,int32_t stride) {
    std::shared_ptr<Sender> sender;
    {
        std::lock_guard<std::mutex> guard(registry_lock);
        auto found=senders.find(handle);
        if(found==senders.end()) return INVALID;
        sender=found->second;
    }
    try { return sender->send(rgb,length,stride); }
    catch(const std::bad_alloc&) { return NO_MEMORY; }
    catch(...) { return IO_ERROR; }
}
API int32_t __cdecl PPF_Close(uint64_t handle) {
    std::shared_ptr<Sender> sender;
    {
        std::lock_guard<std::mutex> guard(registry_lock);
        auto found=senders.find(handle);
        if(found==senders.end()) return INVALID;
        sender=found->second; senders.erase(found);
    }
    // A concurrent in-flight call retains its own shared_ptr until it returns.
    return OK;
}
