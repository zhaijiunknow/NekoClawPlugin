import{d as $,g as T,s as K,e as P,f as B,h as U}from"./index-CucsYwBl.js";import{s as A}from"./index-B804sjqF.js";import{B as z,D as k}from"./index-DHbaENoy.js";import{u,A as h,H as o,E as p,J as m,N as V,q as C,G as E,I as v,p as _,i as I,F as s,B as d,C as f,K as D,L as j,M as N,w as q}from"./style-rM6B2R_a.js";import{u as F,C as G}from"./CoyoteLocalConnStore-BPobZHLz.js";import{_ as W}from"./_plugin-vue_export-helper-DlAUqK2U.js";import"./chartRoutes-VVL9Kqkx.js";var X=function(t){var e=t.dt;return`
.p-slider {
    position: relative;
    background: `.concat(e("slider.track.background"),`;
    border-radius: `).concat(e("slider.border.radius"),`;
}

.p-slider-handle {
    cursor: grab;
    touch-action: none;
    display: flex;
    justify-content: center;
    align-items: center;
    height: `).concat(e("slider.handle.height"),`;
    width: `).concat(e("slider.handle.width"),`;
    background: `).concat(e("slider.handle.background"),`;
    border-radius: `).concat(e("slider.handle.border.radius"),`;
    transition: background `).concat(e("slider.transition.duration"),", color ").concat(e("slider.transition.duration"),", border-color ").concat(e("slider.transition.duration"),", box-shadow ").concat(e("slider.transition.duration"),", outline-color ").concat(e("slider.transition.duration"),`;
    outline-color: transparent;
}

.p-slider-handle::before {
    content: "";
    width: `).concat(e("slider.handle.content.width"),`;
    height: `).concat(e("slider.handle.content.height"),`;
    display: block;
    background: `).concat(e("slider.handle.content.background"),`;
    border-radius: `).concat(e("slider.handle.content.border.radius"),`;
    box-shadow: `).concat(e("slider.handle.content.shadow"),`;
    transition: background `).concat(e("slider.transition.duration"),`;
}

.p-slider:not(.p-disabled) .p-slider-handle:hover {
    background: `).concat(e("slider.handle.hover.background"),`;
}

.p-slider:not(.p-disabled) .p-slider-handle:hover::before {
    background: `).concat(e("slider.handle.content.hover.background"),`;
}

.p-slider-handle:focus-visible {
    border-color: `).concat(e("slider.handle.focus.border.color"),`;
    box-shadow: `).concat(e("slider.handle.focus.ring.shadow"),`;
    outline: `).concat(e("slider.handle.focus.ring.width")," ").concat(e("slider.handle.focus.ring.style")," ").concat(e("slider.handle.focus.ring.color"),`;
    outline-offset: `).concat(e("slider.handle.focus.ring.offset"),`;
}

.p-slider-range {
    display: block;
    background: `).concat(e("slider.range.background"),`;
    border-radius: `).concat(e("slider.border.radius"),`;
}

.p-slider.p-slider-horizontal {
    height: `).concat(e("slider.track.size"),`;
}

.p-slider-horizontal .p-slider-range {
    top: 0;
    left: 0;
    height: 100%;
}

.p-slider-horizontal .p-slider-handle {
    top: 50%;
    margin-top: calc(-1 * calc(`).concat(e("slider.handle.height"),` / 2));
    margin-left: calc(-1 * calc(`).concat(e("slider.handle.width"),` / 2));
}

.p-slider-vertical {
    min-height: 100px;
    width: `).concat(e("slider.track.size"),`;
}

.p-slider-vertical .p-slider-handle {
    left: 50%;
    margin-left: calc(-1 * calc(`).concat(e("slider.handle.width"),` / 2));
    margin-bottom: calc(-1 * calc(`).concat(e("slider.handle.height"),` / 2));
}

.p-slider-vertical .p-slider-range {
    bottom: 0;
    left: 0;
    width: 100%;
}
`)},Y={handle:{position:"absolute"},range:{position:"absolute"}},R={root:function(t){var e=t.props;return["p-slider p-component",{"p-disabled":e.disabled,"p-slider-horizontal":e.orientation==="horizontal","p-slider-vertical":e.orientation==="vertical"}]},range:"p-slider-range",handle:"p-slider-handle"},J=z.extend({name:"slider",theme:X,classes:R,inlineStyles:Y}),O={name:"BaseSlider",extends:$,props:{modelValue:[Number,Array],min:{type:Number,default:0},max:{type:Number,default:100},orientation:{type:String,default:"horizontal"},step:{type:Number,default:null},range:{type:Boolean,default:!1},disabled:{type:Boolean,default:!1},tabindex:{type:Number,default:0},ariaLabelledby:{type:String,default:null},ariaLabel:{type:String,default:null}},style:J,provide:function(){return{$pcSlider:this,$parentInstance:this}}};function Q(n){return te(n)||ne(n)||ee(n)||Z()}function Z(){throw new TypeError(`Invalid attempt to spread non-iterable instance.
In order to be iterable, non-array objects must have a [Symbol.iterator]() method.`)}function ee(n,t){if(n){if(typeof n=="string")return L(n,t);var e={}.toString.call(n).slice(8,-1);return e==="Object"&&n.constructor&&(e=n.constructor.name),e==="Map"||e==="Set"?Array.from(n):e==="Arguments"||/^(?:Ui|I)nt(?:8|16|32)(?:Clamped)?Array$/.test(e)?L(n,t):void 0}}function ne(n){if(typeof Symbol<"u"&&n[Symbol.iterator]!=null||n["@@iterator"]!=null)return Array.from(n)}function te(n){if(Array.isArray(n))return L(n)}function L(n,t){(t==null||t>n.length)&&(t=n.length);for(var e=0,r=Array(t);e<t;e++)r[e]=n[e];return r}var M={name:"Slider",extends:O,inheritAttrs:!1,emits:["update:modelValue","change","slideend"],dragging:!1,handleIndex:null,initX:null,initY:null,barWidth:null,barHeight:null,dragListener:null,dragEndListener:null,beforeUnmount:function(){this.unbindDragListeners()},methods:{updateDomData:function(){var t=this.$el.getBoundingClientRect();this.initX=t.left+k.getWindowScrollLeft(),this.initY=t.top+k.getWindowScrollTop(),this.barWidth=this.$el.offsetWidth,this.barHeight=this.$el.offsetHeight},setValue:function(t){var e,r=t.touches?t.touches[0].pageX:t.pageX,i=t.touches?t.touches[0].pageY:t.pageY;this.orientation==="horizontal"?e=(r-this.initX)*100/this.barWidth:e=(this.initY+this.barHeight-i)*100/this.barHeight;var l=(this.max-this.min)*(e/100)+this.min;if(this.step){var a=this.range?this.value[this.handleIndex]:this.value,g=l-a;g<0?l=a+Math.ceil(l/this.step-a/this.step)*this.step:g>0&&(l=a+Math.floor(l/this.step-a/this.step)*this.step)}else l=Math.floor(l);this.updateModel(t,l)},updateModel:function(t,e){var r=parseFloat(e.toFixed(10)),i;this.range?(i=this.value?Q(this.value):[],this.handleIndex==0?(r<this.min?r=this.min:r>=this.max&&(r=this.max),i[0]=r):(r>this.max?r=this.max:r<=this.min&&(r=this.min),i[1]=r)):(r<this.min?r=this.min:r>this.max&&(r=this.max),i=r),this.$emit("update:modelValue",i),this.$emit("change",i)},onDragStart:function(t,e){this.disabled||(this.$el.setAttribute("data-p-sliding",!0),this.dragging=!0,this.updateDomData(),this.range&&this.value[0]===this.max?this.handleIndex=0:this.handleIndex=e,t.currentTarget.focus(),t.preventDefault())},onDrag:function(t){this.dragging&&(this.setValue(t),t.preventDefault())},onDragEnd:function(t){this.dragging&&(this.dragging=!1,this.$el.setAttribute("data-p-sliding",!1),this.$emit("slideend",{originalEvent:t,value:this.value}))},onBarClick:function(t){this.disabled||k.getAttribute(t.target,"data-pc-section")!=="handle"&&(this.updateDomData(),this.setValue(t))},onMouseDown:function(t,e){this.bindDragListeners(),this.onDragStart(t,e)},onKeyDown:function(t,e){switch(this.handleIndex=e,t.code){case"ArrowDown":case"ArrowLeft":this.decrementValue(t,e),t.preventDefault();break;case"ArrowUp":case"ArrowRight":this.incrementValue(t,e),t.preventDefault();break;case"PageDown":this.decrementValue(t,e,!0),t.preventDefault();break;case"PageUp":this.incrementValue(t,e,!0),t.preventDefault();break;case"Home":this.updateModel(t,this.min),t.preventDefault();break;case"End":this.updateModel(t,this.max),t.preventDefault();break}},decrementValue:function(t,e){var r=arguments.length>2&&arguments[2]!==void 0?arguments[2]:!1,i;this.range?this.step?i=this.value[e]-this.step:i=this.value[e]-1:this.step?i=this.value-this.step:!this.step&&r?i=this.value-10:i=this.value-1,this.updateModel(t,i),t.preventDefault()},incrementValue:function(t,e){var r=arguments.length>2&&arguments[2]!==void 0?arguments[2]:!1,i;this.range?this.step?i=this.value[e]+this.step:i=this.value[e]+1:this.step?i=this.value+this.step:!this.step&&r?i=this.value+10:i=this.value+1,this.updateModel(t,i),t.preventDefault()},bindDragListeners:function(){this.dragListener||(this.dragListener=this.onDrag.bind(this),document.addEventListener("mousemove",this.dragListener)),this.dragEndListener||(this.dragEndListener=this.onDragEnd.bind(this),document.addEventListener("mouseup",this.dragEndListener))},unbindDragListeners:function(){this.dragListener&&(document.removeEventListener("mousemove",this.dragListener),this.dragListener=null),this.dragEndListener&&(document.removeEventListener("mouseup",this.dragEndListener),this.dragEndListener=null)}},computed:{value:function(){var t;if(this.range){var e,r,i,l;return[(e=(r=this.modelValue)===null||r===void 0?void 0:r[0])!==null&&e!==void 0?e:this.min,(i=(l=this.modelValue)===null||l===void 0?void 0:l[1])!==null&&i!==void 0?i:this.max]}return(t=this.modelValue)!==null&&t!==void 0?t:this.min},horizontal:function(){return this.orientation==="horizontal"},vertical:function(){return this.orientation==="vertical"},rangeStyle:function(){if(this.range){var t=this.rangeEndPosition>this.rangeStartPosition?this.rangeEndPosition-this.rangeStartPosition:this.rangeStartPosition-this.rangeEndPosition,e=this.rangeEndPosition>this.rangeStartPosition?this.rangeStartPosition:this.rangeEndPosition;return this.horizontal?{left:e+"%",width:t+"%"}:{bottom:e+"%",height:t+"%"}}else return this.horizontal?{width:this.handlePosition+"%"}:{height:this.handlePosition+"%"}},handleStyle:function(){return this.horizontal?{left:this.handlePosition+"%"}:{bottom:this.handlePosition+"%"}},handlePosition:function(){return this.value<this.min?0:this.value>this.max?100:(this.value-this.min)*100/(this.max-this.min)},rangeStartPosition:function(){return this.value&&this.value[0]?(this.value[0]<this.min?0:this.value[0]-this.min)*100/(this.max-this.min):0},rangeEndPosition:function(){return this.value&&this.value.length===2?(this.value[1]>this.max?100:this.value[1]-this.min)*100/(this.max-this.min):100},rangeStartHandleStyle:function(){return this.horizontal?{left:this.rangeStartPosition+"%"}:{bottom:this.rangeStartPosition+"%"}},rangeEndHandleStyle:function(){return this.horizontal?{left:this.rangeEndPosition+"%"}:{bottom:this.rangeEndPosition+"%"}}}},ie=["tabindex","aria-valuemin","aria-valuenow","aria-valuemax","aria-labelledby","aria-label","aria-orientation"],ae=["tabindex","aria-valuemin","aria-valuenow","aria-valuemax","aria-labelledby","aria-label","aria-orientation"],oe=["tabindex","aria-valuemin","aria-valuenow","aria-valuemax","aria-labelledby","aria-label","aria-orientation"];function le(n,t,e,r,i,l){return u(),h("div",p({class:n.cx("root"),onClick:t[15]||(t[15]=function(){return l.onBarClick&&l.onBarClick.apply(l,arguments)})},n.ptmi("root"),{"data-p-sliding":!1}),[o("span",p({class:n.cx("range"),style:[n.sx("range"),l.rangeStyle]},n.ptm("range")),null,16),n.range?m("",!0):(u(),h("span",p({key:0,class:n.cx("handle"),style:[n.sx("handle"),l.handleStyle],onTouchstartPassive:t[0]||(t[0]=function(a){return l.onDragStart(a)}),onTouchmovePassive:t[1]||(t[1]=function(a){return l.onDrag(a)}),onTouchend:t[2]||(t[2]=function(a){return l.onDragEnd(a)}),onMousedown:t[3]||(t[3]=function(a){return l.onMouseDown(a)}),onKeydown:t[4]||(t[4]=function(a){return l.onKeyDown(a)}),tabindex:n.tabindex,role:"slider","aria-valuemin":n.min,"aria-valuenow":n.modelValue,"aria-valuemax":n.max,"aria-labelledby":n.ariaLabelledby,"aria-label":n.ariaLabel,"aria-orientation":n.orientation},n.ptm("handle")),null,16,ie)),n.range?(u(),h("span",p({key:1,class:n.cx("handle"),style:[n.sx("handle"),l.rangeStartHandleStyle],onTouchstartPassive:t[5]||(t[5]=function(a){return l.onDragStart(a,0)}),onTouchmovePassive:t[6]||(t[6]=function(a){return l.onDrag(a)}),onTouchend:t[7]||(t[7]=function(a){return l.onDragEnd(a)}),onMousedown:t[8]||(t[8]=function(a){return l.onMouseDown(a,0)}),onKeydown:t[9]||(t[9]=function(a){return l.onKeyDown(a,0)}),tabindex:n.tabindex,role:"slider","aria-valuemin":n.min,"aria-valuenow":n.modelValue?n.modelValue[0]:null,"aria-valuemax":n.max,"aria-labelledby":n.ariaLabelledby,"aria-label":n.ariaLabel,"aria-orientation":n.orientation},n.ptm("startHandler")),null,16,ae)):m("",!0),n.range?(u(),h("span",p({key:2,class:n.cx("handle"),style:[n.sx("handle"),l.rangeEndHandleStyle],onTouchstartPassive:t[10]||(t[10]=function(a){return l.onDragStart(a,1)}),onTouchmovePassive:t[11]||(t[11]=function(a){return l.onDrag(a)}),onTouchend:t[12]||(t[12]=function(a){return l.onDragEnd(a)}),onMousedown:t[13]||(t[13]=function(a){return l.onMouseDown(a,1)}),onKeydown:t[14]||(t[14]=function(a){return l.onKeyDown(a,1)}),tabindex:n.tabindex,role:"slider","aria-valuemin":n.min,"aria-valuenow":n.modelValue?n.modelValue[1]:null,"aria-valuemax":n.max,"aria-labelledby":n.ariaLabelledby,"aria-label":n.ariaLabel,"aria-orientation":n.orientation},n.ptm("endHandler")),null,16,oe)):m("",!0)],16)}M.render=le;var re=function(t){var e=t.dt;return`
.p-divider-horizontal {
    display: flex;
    width: 100%;
    position: relative;
    align-items: center;
    margin: `.concat(e("divider.horizontal.margin"),`;
    padding: `).concat(e("divider.horizontal.padding"),`;
}

.p-divider-horizontal:before {
    position: absolute;
    display: block;
    top: 50%;
    left: 0;
    width: 100%;
    content: "";
    border-top: 1px solid `).concat(e("divider.border.color"),`;
}

.p-divider-horizontal .p-divider-content {
    padding: `).concat(e("divider.horizontal.content.padding"),`;
}

.p-divider-vertical {
    min-height: 100%;
    margin: 0 1rem;
    display: flex;
    position: relative;
    justify-content: center;
    margin: `).concat(e("divider.vertical.margin"),`;
    padding: `).concat(e("divider.vertical.padding"),`;
}

.p-divider-vertical:before {
    position: absolute;
    display: block;
    top: 0;
    left: 50%;
    height: 100%;
    content: "";
    border-left: 1px solid `).concat(e("divider.border.color"),`;
}

.p-divider.p-divider-vertical .p-divider-content {
    padding: `).concat(e("divider.vertical.content.padding"),`;
}

.p-divider-content {
    z-index: 1;
    background: `).concat(e("divider.content.background"),`;
    color: `).concat(e("divider.content.color"),`;
}

.p-divider-solid.p-divider-horizontal:before {
    border-top-style: solid;
}

.p-divider-solid.p-divider-vertical:before {
    border-left-style: solid;
}

.p-divider-dashed.p-divider-horizontal:before {
    border-top-style: dashed;
}

.p-divider-dashed.p-divider-vertical:before {
    border-left-style: dashed;
}

.p-divider-dotted.p-divider-horizontal:before {
    border-top-style: dotted;
}

.p-divider-dotted.p-divider-vertical:before {
    border-left-style: dotted;
}
`)},se={root:function(t){var e=t.props;return{justifyContent:e.layout==="horizontal"?e.align==="center"||e.align===null?"center":e.align==="left"?"flex-start":e.align==="right"?"flex-end":null:null,alignItems:e.layout==="vertical"?e.align==="center"||e.align===null?"center":e.align==="top"?"flex-start":e.align==="bottom"?"flex-end":null:null}}},de={root:function(t){var e=t.props;return["p-divider p-component","p-divider-"+e.layout,"p-divider-"+e.type,{"p-divider-left":e.layout==="horizontal"&&(!e.align||e.align==="left")},{"p-divider-center":e.layout==="horizontal"&&e.align==="center"},{"p-divider-right":e.layout==="horizontal"&&e.align==="right"},{"p-divider-top":e.layout==="vertical"&&e.align==="top"},{"p-divider-center":e.layout==="vertical"&&(!e.align||e.align==="center")},{"p-divider-bottom":e.layout==="vertical"&&e.align==="bottom"}]},content:"p-divider-content"},ce=z.extend({name:"divider",theme:re,classes:de,inlineStyles:se}),ue={name:"BaseDivider",extends:$,props:{align:{type:String,default:null},layout:{type:String,default:"horizontal"},type:{type:String,default:"solid"}},style:ce,provide:function(){return{$pcDivider:this,$parentInstance:this}}},H={name:"Divider",extends:ue,inheritAttrs:!1},he=["aria-orientation"];function pe(n,t,e,r,i,l){return u(),h("div",p({class:n.cx("root"),style:n.sx("root"),role:"separator","aria-orientation":n.layout},n.ptmi("root")),[n.$slots.default?(u(),h("div",p({key:0,class:n.cx("content")},n.ptm("content")),[V(n.$slots,"default")],16)):m("",!0)],16,he)}H.render=pe;var me=function(t){var e=t.dt;return`
.p-chip {
    display: inline-flex;
    align-items: center;
    background: `.concat(e("chip.background"),`;
    color: `).concat(e("chip.color"),`;
    border-radius: `).concat(e("chip.border.radius"),`;
    padding: `).concat(e("chip.padding.y")," ").concat(e("chip.padding.x"),`;
    gap: `).concat(e("chip.gap"),`;
}

.p-chip-icon {
    color: `).concat(e("chip.icon.color"),`;
    font-size: `).concat(e("chip.icon.font.size"),`;
    width: `).concat(e("chip.icon.size"),`;
    height: `).concat(e("chip.icon.size"),`;
}

.p-chip-image {
    border-radius: 50%;
    width: `).concat(e("chip.image.width"),`;
    height: `).concat(e("chip.image.height"),`;
    margin-left: calc(-1 * `).concat(e("chip.padding.y"),`);
}

.p-chip:has(.p-chip-remove-icon) {
    padding-right: `).concat(e("chip.padding.y"),`;
}

.p-chip:has(.p-chip-image) {
    padding-top: calc(`).concat(e("chip.padding.y"),` / 2);
    padding-bottom: calc(`).concat(e("chip.padding.y"),` / 2);
}

.p-chip-remove-icon {
    cursor: pointer;
    font-size: `).concat(e("chip.remove.icon.font.size"),`;
    width: `).concat(e("chip.remove.icon.size"),`;
    height: `).concat(e("chip.remove.icon.size"),`;
    color: `).concat(e("chip.remove.icon.color"),`;
    border-radius: 50%;
    transition: outline-color `).concat(e("chip.transition.duration"),", box-shadow ").concat(e("chip.transition.duration"),`;
    outline-color: transparent;
}

.p-chip-remove-icon:focus-visible {
    box-shadow: `).concat(e("chip.remove.icon.focus.ring.shadow"),`;
    outline: `).concat(e("chip.remove.icon.focus.ring.width")," ").concat(e("chip.remove.icon.focus.ring.style")," ").concat(e("chip.remove.icon.focus.ring.color"),`;
    outline-offset: `).concat(e("chip.remove.icon.focus.ring.offset"),`;
}
`)},fe={root:"p-chip p-component",image:"p-chip-image",icon:"p-chip-icon",label:"p-chip-label",removeIcon:"p-chip-remove-icon"},ge=z.extend({name:"chip",theme:me,classes:fe}),ve={name:"BaseChip",extends:$,props:{label:{type:String,default:null},icon:{type:String,default:null},image:{type:String,default:null},removable:{type:Boolean,default:!1},removeIcon:{type:String,default:void 0}},style:ge,provide:function(){return{$pcChip:this,$parentInstance:this}}},S={name:"Chip",extends:ve,inheritAttrs:!1,emits:["remove"],data:function(){return{visible:!0}},methods:{onKeydown:function(t){(t.key==="Enter"||t.key==="Backspace")&&this.close(t)},close:function(t){this.visible=!1,this.$emit("remove",t)}},components:{TimesCircleIcon:T}},be=["aria-label"],ye=["src"];function we(n,t,e,r,i,l){return i.visible?(u(),h("div",p({key:0,class:n.cx("root"),"aria-label":n.label},n.ptmi("root")),[V(n.$slots,"default",{},function(){return[n.image?(u(),h("img",p({key:0,src:n.image},n.ptm("image"),{class:n.cx("image")}),null,16,ye)):n.$slots.icon?(u(),C(E(n.$slots.icon),p({key:1,class:n.cx("icon")},n.ptm("icon")),null,16,["class"])):n.icon?(u(),h("span",p({key:2,class:[n.cx("icon"),n.icon]},n.ptm("icon")),null,16)):m("",!0),n.label?(u(),h("div",p({key:3,class:n.cx("label")},n.ptm("label")),v(n.label),17)):m("",!0)]}),n.removable?V(n.$slots,"removeicon",{key:0,removeCallback:l.close,keydownCallback:l.onKeydown},function(){return[(u(),C(E(n.removeIcon?"span":"TimesCircleIcon"),p({tabindex:"0",class:[n.cx("removeIcon"),n.removeIcon],onClick:l.close,onKeydown:l.onKeydown},n.ptm("removeIcon")),null,16,["class","onClick","onKeydown"]))]}):m("",!0)],16,be)):m("",!0)}S.render=we;const xe={xmlns:"http://www.w3.org/2000/svg",width:"257.031",height:"200",class:"icon",viewBox:"0 0 1316 1024"},Se=o("path",{fill:"currentColor",d:"M1097.143 292.571V731.43H146.286V292.57zm73.143 329.143h73.143V402.286h-73.143V237.714c0-10.276-8.01-18.285-18.286-18.285H91.429c-10.277 0-18.286 8.009-18.286 18.285v548.572c0 10.276 8.009 18.285 18.286 18.285H1152c10.277 0 18.286-8.009 18.286-18.285zm146.285-219.428v219.428a72.936 72.936 0 0 1-73.142 73.143v91.429c0 50.285-41.143 91.428-91.429 91.428H91.429A91.685 91.685 0 0 1 0 786.286V237.714c0-50.285 41.143-91.428 91.429-91.428H1152c50.286 0 91.429 41.143 91.429 91.428v91.429a72.936 72.936 0 0 1 73.142 73.143"},null,-1),ke=[Se];function Ve(n,t){return u(),h("svg",xe,[...ke])}const De={render:Ve},w=n=>(j("data-v-c433abbf"),n=n(),N(),n),Le={key:0,class:"pb-2"},$e={class:"flex flex-row justify-between gap-2 mt-4 mb-4 items-start md:items-center"},ze=w(()=>o("h2",{class:"font-bold text-xl"},"蓝牙连接",-1)),Ce={class:"flex gap-2 items-center"},Ee={class:"w-full flex flex-col md:flex-row gap-2 lg:gap-8 mb-8 lg:mb-6"},Ie={class:"bg-primary text-primary-contrast rounded-full w-10 h-10 flex-shrink-0 flex items-center justify-center"},Pe={class:"w-full text-center font-semibold text-lg"},Be=w(()=>o("div",{class:"bg-primary text-primary-contrast rounded-full w-10 h-10 flex-shrink-0 flex items-center justify-center"},[o("i",{class:"pi pi-bolt"}),o("span",{class:"ml-[-2px]"},"A")],-1)),Ae={class:"w-full text-center font-semibold text-lg"},_e=w(()=>o("div",{class:"bg-primary text-primary-contrast rounded-full w-10 h-10 flex-shrink-0 flex items-center justify-center"},[o("i",{class:"pi pi-bolt"}),o("span",{class:"ml-[-2px]"},"B")],-1)),Me={class:"w-full text-center font-semibold text-lg"},He={key:0,class:"w-full flex flex-col md:flex-row items-top lg:items-center gap-2 lg:gap-8 mb-8 lg:mb-4"},Te=w(()=>o("label",{class:"font-semibold w-30"},"频率平衡参数",-1)),Ke={class:"w-full flex flex-col md:flex-row items-top lg:items-center gap-2 lg:gap-8 mb-8 lg:mb-4"},Ue=w(()=>o("label",{class:"font-semibold w-30 flex-shrink-0"},"强度上限",-1)),je={class:"w-full flex flex-row gap-4"},Ne=_({name:"CoyoteBluetoothPanel",__name:"CoyoteLocalConnectPanel",setup(n){const t=F(),e=I("parentToast"),r=I("parentConfirm"),i=()=>{r==null||r.require({header:"断开蓝牙连接",message:"确定要断开蓝牙连接吗？",icon:"pi pi-exclamation-triangle",acceptLabel:"确定",rejectLabel:"取消",rejectProps:{severity:"secondary"},accept:async()=>{t.disconnect(),e==null||e.add({severity:"success",summary:"断开成功",detail:"已断开蓝牙连接",life:3e3})}})};return(l,a)=>{const g=H,b=P,x=A,c=B;return s(t).connected?(u(),h("div",Le,[d(g),o("div",$e,[ze,o("div",Ce,[d(s(K),{icon:"pi pi-times",label:"断开",severity:"secondary",onClick:i})])]),o("div",Ee,[d(s(S),{class:"py-0 pl-0 w-full"},{default:f(()=>[o("div",Ie,[d(s(De),{class:"w-5 h-5"})]),o("div",Pe,v(s(t).deviceBattery)+"%",1)]),_:1}),d(s(S),{class:"py-0 pl-0 w-full"},{default:f(()=>[Be,o("div",Ae,v(s(t).deviceStrengthA),1)]),_:1}),d(s(S),{class:"py-0 pl-0 w-full"},{default:f(()=>[_e,o("div",Me,v(s(t).deviceStrengthB),1)]),_:1})]),s(t).deviceVersion===s(G).V2?(u(),h("div",He,[Te,d(b,{class:"input-small",modelValue:s(t).freqBalance,"onUpdate:modelValue":a[0]||(a[0]=y=>s(t).freqBalance=y),min:0,max:200},null,8,["modelValue"])])):m("",!0),o("div",Ke,[Ue,o("div",je,[d(c,null,{default:f(()=>[d(x,null,{default:f(()=>[D("A")]),_:1}),d(b,{modelValue:s(t).inputLimitA,"onUpdate:modelValue":a[1]||(a[1]=y=>s(t).inputLimitA=y),min:1,max:200},null,8,["modelValue"])]),_:1}),d(c,null,{default:f(()=>[d(x,null,{default:f(()=>[D("B")]),_:1}),d(b,{modelValue:s(t).inputLimitB,"onUpdate:modelValue":a[2]||(a[2]=y=>s(t).inputLimitB=y),min:1,max:200},null,8,["modelValue"])]),_:1})])])])):m("",!0)}}}),qe=W(Ne,[["__scopeId","data-v-c433abbf"]]),Fe={class:"w-full"},Ge={class:"w-full flex flex-col md:flex-row items-top lg:items-center gap-2 lg:gap-8 mb-8 lg:mb-4"},We=o("label",{class:"font-semibold w-35 flex-shrink-0"},"强度变化频率",-1),Xe={class:"w-full flex-shrink flex gap-2 flex-col lg:items-center lg:flex-row lg:gap-8"},Ye={class:"h-6 lg:h-auto flex-grow flex items-center"},Re={class:"w-40"},Je={class:"w-full flex flex-col md:flex-row items-top lg:items-center gap-2 lg:gap-8 mb-8 lg:mb-4"},Oe=o("label",{class:"font-semibold w-35"},"基础强度",-1),Qe=o("div",{class:"flex-grow flex-shrink"},null,-1),Ze={class:"w-full flex flex-col md:flex-row items-top lg:items-center gap-2 lg:gap-8 mb-8 lg:mb-4"},en=o("label",{class:"font-semibold w-35"},"随机强度",-1),nn=o("div",{class:"flex-grow flex-shrink"},null,-1),tn={class:"flex gap-8 mb-4 w-full"},an=o("div",{class:"w-35"},null,-1),on={class:"opacity-60 text-right"},ln={class:"w-full flex flex-col md:flex-row items-top lg:items-center gap-2 lg:gap-8 mb-8 lg:mb-4"},rn=o("label",{class:"font-semibold w-35"},"一键开火强度限制",-1),sn=o("div",{class:"flex-grow flex-shrink"},null,-1),dn={class:"flex items-center gap-2 lg:gap-8 mb-4 w-full"},cn=o("label",{class:"font-semibold w-35"},"B通道",-1),un={class:"w-full flex flex-col md:flex-row items-top lg:items-center gap-2 lg:gap-8 mb-8 lg:mb-4"},hn=o("label",{class:"font-semibold w-35"},"B通道强度倍数",-1),pn=o("div",{class:"flex-grow flex-shrink"},null,-1),mn=o("div",{class:"flex gap-8 w-full"},[o("div",{class:"w-35"}),o("div",{class:"opacity-60 text-right"}," B通道的强度 = A通道强度 * 强度倍数 ")],-1),Sn=_({name:"StrengthSettings",__name:"StrengthSettings",props:{state:{}},setup(n){const t=n;let e;return q(()=>t.state,r=>{e=r},{immediate:!0}),(r,i)=>{const l=M,a=P,g=A,b=B,x=U;return u(),h("div",Fe,[o("div",Ge,[We,o("div",Xe,[o("div",Ye,[d(l,{class:"w-full",modelValue:s(e).randomFreq,"onUpdate:modelValue":i[0]||(i[0]=c=>s(e).randomFreq=c),range:"",max:60},null,8,["modelValue"])]),o("div",Re,[d(b,{class:"input-small"},{default:f(()=>[d(a,{class:"input-text-center",modelValue:s(e).randomFreq[0],"onUpdate:modelValue":i[1]||(i[1]=c=>s(e).randomFreq[0]=c)},null,8,["modelValue"]),d(g,null,{default:f(()=>[D("-")]),_:1}),d(a,{class:"input-text-center",modelValue:s(e).randomFreq[1],"onUpdate:modelValue":i[2]||(i[2]=c=>s(e).randomFreq[1]=c)},null,8,["modelValue"])]),_:1})])])]),o("div",Je,[Oe,d(a,{class:"input-small",modelValue:s(e).strengthVal,"onUpdate:modelValue":i[3]||(i[3]=c=>s(e).strengthVal=c)},null,8,["modelValue"]),Qe]),o("div",Ze,[en,d(a,{class:"input-small",modelValue:s(e).randomStrengthVal,"onUpdate:modelValue":i[4]||(i[4]=c=>s(e).randomStrengthVal=c)},null,8,["modelValue"]),nn]),o("div",tn,[an,o("div",on," 强度范围："+v(s(e).strengthVal)+" - "+v(s(e).strengthVal+s(e).randomStrengthVal)+"，强度上限请在DG-Lab中设置 ",1)]),o("div",ln,[rn,d(a,{class:"input-small",modelValue:s(e).fireStrengthLimit,"onUpdate:modelValue":i[5]||(i[5]=c=>s(e).fireStrengthLimit=c)},null,8,["modelValue"]),sn]),o("div",dn,[cn,d(x,{modelValue:s(e).bChannelEnabled,"onUpdate:modelValue":i[6]||(i[6]=c=>s(e).bChannelEnabled=c),onIcon:"pi pi-circle-on",onLabel:"已启用",offIcon:"pi pi-circle-off",offLabel:"已禁用"},null,8,["modelValue"])]),o("div",un,[hn,d(a,{class:"input-small",disabled:!s(e).bChannelEnabled,modelValue:s(e).bChannelMultiple,"onUpdate:modelValue":i[7]||(i[7]=c=>s(e).bChannelMultiple=c)},null,8,["disabled","modelValue"]),pn]),mn,d(qe)])}}});export{Sn as default};
