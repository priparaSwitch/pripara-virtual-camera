// Direct factory/metadata probe; no registration, system device enumeration,
// graph, connection, Run/Pause, streaming thread, FillBuffer or Receive call.
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <dshow.h>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>
#include <stdexcept>

namespace {
struct Failure : std::runtime_error { using std::runtime_error::runtime_error; };
void require(bool condition,const char* message) {
    if(!condition) throw Failure(message);
}
void success(HRESULT result,const char* message) {
    if(result!=S_OK) {
        std::fprintf(stderr,"%s: HRESULT=0x%08lx\n",message,
                     static_cast<unsigned long>(result));
        throw Failure(message);
    }
}
template<class T> struct Com {
    T* value=nullptr;
    ~Com() { if(value) value->Release(); }
    T** address() { return &value; }
    T* operator->() const { return value; }
};
struct Module {
    HMODULE handle=nullptr;
    ~Module() { if(handle) FreeLibrary(handle); }
};
struct Media {
    AM_MEDIA_TYPE* type=nullptr;
    ~Media() {
        if(!type) return;
        if(type->pUnk) type->pUnk->Release();
        CoTaskMemFree(type->pbFormat);
        CoTaskMemFree(type);
    }
};
struct Video {
    LONG width,height;
    WORD bitCount;
    DWORD compression,imageBytes;
    REFERENCE_TIME frameInterval;
    bool yuy2;
};
Video inspect(AM_MEDIA_TYPE* media) {
    require(media && media->majortype==MEDIATYPE_Video,"Video major type");
    require(media->formattype==FORMAT_VideoInfo,"VideoInfo format");
    require(media->cbFormat>=sizeof(VIDEOINFOHEADER) && media->pbFormat,
            "Complete VIDEOINFOHEADER");
    auto* info=reinterpret_cast<VIDEOINFOHEADER*>(media->pbFormat);
    require(info->bmiHeader.biSize>=sizeof(BITMAPINFOHEADER),"Bitmap header");
    return {info->bmiHeader.biWidth,info->bmiHeader.biHeight,
            info->bmiHeader.biBitCount,info->bmiHeader.biCompression,
            info->bmiHeader.biSizeImage,info->AvgTimePerFrame,
            media->subtype==MEDIASUBTYPE_YUY2};
}
void video_json(const Video& video) {
    std::printf("{\"width\":%ld,\"height\":%ld,\"bits\":%u,"
                "\"compression\":%lu,\"imageBytes\":%lu,"
                "\"frameInterval100ns\":%lld,\"yuy2\":%s}",
                video.width,video.height,unsigned(video.bitCount),
                static_cast<unsigned long>(video.compression),
                static_cast<unsigned long>(video.imageBytes),
                static_cast<long long>(video.frameInterval),video.yuy2?"true":"false");
}
}

int wmain(int argc,wchar_t** argv) {
    try {
        require(argc==3,"Usage: filter_abi_probe <built-DLL> upper|qr");
        const bool qr=std::wstring(argv[2])==L"qr";
        require(qr || std::wstring(argv[2])==L"upper","Known filter kind");
        Module module;
        module.handle=LoadLibraryExW(argv[1],nullptr,
                        LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR|LOAD_LIBRARY_SEARCH_SYSTEM32);
        require(module.handle!=nullptr,"LoadLibraryEx built filter");
        using GetFactory=HRESULT(STDAPICALLTYPE*)(REFCLSID,REFIID,void**);
        auto getFactory=reinterpret_cast<GetFactory>(
                             GetProcAddress(module.handle,"DllGetClassObject"));
        require(getFactory!=nullptr,"DllGetClassObject export");
        CLSID clsid={0x5c2cd55c,0x92ad,0x4999,{0x86,0x66,0x91,0x2b,0xd3,0xe7,0,
                    static_cast<BYTE>((sizeof(void*)==8?0x10:0x20)+(qr?2:0))}};
        Com<IClassFactory> factory;
        success(getFactory(clsid,IID_IClassFactory,
                    reinterpret_cast<void**>(factory.address())),"Class factory");
        Com<IBaseFilter> filter;
        success(factory->CreateInstance(nullptr,IID_IBaseFilter,
                    reinterpret_cast<void**>(filter.address())),"Create IBaseFilter");
        FILTER_STATE state=State_Running;
        success(filter->GetState(0,&state),"Get initial filter state");
        require(state==State_Stopped,"Filter remains stopped");
        Com<IEnumPins> pins;
        success(filter->EnumPins(pins.address()),"EnumPins");
        Com<IPin> pin;
        success(pins->Next(1,pin.address(),nullptr),"One output pin");
        PIN_DIRECTION direction=PINDIR_INPUT;
        success(pin->QueryDirection(&direction),"QueryDirection");
        require(direction==PINDIR_OUTPUT,"Output pin direction");
        Com<IPin> extra;
        require(pins->Next(1,extra.address(),nullptr)==S_FALSE,"Exactly one pin");

        Com<IEnumMediaTypes> mediaTypes;
        success(pin->EnumMediaTypes(mediaTypes.address()),"EnumMediaTypes");
        std::vector<Video> enumerated;
        for(int i=0;i<128;++i) {
            Media media;
            HRESULT result=mediaTypes->Next(1,&media.type,nullptr);
            if(result==S_FALSE) break;
            success(result,"Enumerate media type");
            enumerated.push_back(inspect(media.type));
        }
        require(!enumerated.empty() && enumerated.size()<128,"Finite media types");
        Com<IAMStreamConfig> config;
        success(pin->QueryInterface(IID_IAMStreamConfig,
                    reinterpret_cast<void**>(config.address())),"IAMStreamConfig");
        int count=0,size=0;
        success(config->GetNumberOfCapabilities(&count,&size),"Capability count");
        require(count>0 && count<128 && size==sizeof(VIDEO_STREAM_CONFIG_CAPS),
                "Video stream capability ABI");
        Media format;
        success(config->GetFormat(&format.type),"Default format");
        const Video defaultVideo=inspect(format.type);
        Media capability;
        VIDEO_STREAM_CONFIG_CAPS caps{};
        success(config->GetStreamCaps(0,&capability.type,
                    reinterpret_cast<BYTE*>(&caps)),"First stream capability");
        const Video capVideo=inspect(capability.type);
        if(qr) {
            require(count==1 && enumerated.size()==1,"One QR media type");
            for(const auto& video:{defaultVideo,capVideo,enumerated.front()})
                require(video.width==640 && video.height==480 && video.bitCount==16 &&
                        video.yuy2 && video.compression==MAKEFOURCC('Y','U','Y','2') &&
                        video.imageBytes==614400,"QR 640x480 YUY2 bytes");
            require(caps.MinOutputSize.cx==640 && caps.MaxOutputSize.cx==640 &&
                    caps.MinOutputSize.cy==480 && caps.MaxOutputSize.cy==480,
                    "Fixed QR output dimensions");
        }

        Com<IAMCameraControl> control;
        HRESULT controlResult=filter->QueryInterface(IID_IAMCameraControl,
                                reinterpret_cast<void**>(control.address()));
        struct Control { long property,minimum,maximum,step,defaultValue,flags; };
        std::vector<Control> ranges;
        if(qr) {
            success(controlResult,"QR IAMCameraControl");
            for(long property=CameraControl_Pan;property<=CameraControl_Focus;++property) {
                Control item{property,0,0,0,0,0};
                success(control->GetRange(property,&item.minimum,&item.maximum,
                    &item.step,&item.defaultValue,&item.flags),"QR GetRange");
                long fixed=property==CameraControl_Zoom?100:0;
                require(item.minimum==fixed && item.maximum==fixed &&
                        item.defaultValue==fixed && item.step==1 &&
                        item.flags==CameraControl_Flags_Manual,"Fixed manual controls");
                ranges.push_back(item);
            }
        } else require(controlResult==E_NOINTERFACE,"Upper unchanged control interface");
        std::printf("{\"passed\":true,\"bits\":%u,\"kind\":\"%s\","
                    "\"clsidLastByte\":%u,\"initialStopped\":true,"
                    "\"outputPins\":1,\"mediaTypeCount\":%u,"
                    "\"capabilityCount\":%d,\"capabilityStructBytes\":%d,"
                    "\"defaultFormat\":",unsigned(sizeof(void*)*8),qr?"qr":"upper",
                    unsigned(clsid.Data4[7]),unsigned(enumerated.size()),count,size);
        video_json(defaultVideo);
        std::printf(",\"firstCapability\":"); video_json(capVideo);
        std::printf(",\"cameraControl\":%s,\"controlRanges\":[",qr?"true":"false");
        for(size_t i=0;i<ranges.size();++i) {
            const auto& r=ranges[i];
            std::printf("%s{\"property\":%ld,\"min\":%ld,\"max\":%ld,"
                "\"step\":%ld,\"default\":%ld,\"flags\":%ld}",i?",":"",
                r.property,r.minimum,r.maximum,r.step,r.defaultValue,r.flags);
        }
        std::printf("],\"registrationCalled\":false,\"systemDeviceEnumeration\":false,"
                    "\"runPauseOrConnectCalled\":false,\"frameReceiverCalled\":false}\n");
        return 0;
    } catch(const std::exception& error) {
        std::fprintf(stderr,"Filter ABI validation failed: %s\n",error.what());
        return 1;
    }
}
