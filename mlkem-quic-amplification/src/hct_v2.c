#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <math.h>
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <unistd.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <arpa/inet.h>
#include <openssl/ssl.h>
#include <openssl/err.h>
#include <openssl/objects.h>

static double now_ms(void){struct timespec ts;clock_gettime(CLOCK_MONOTONIC,&ts);
    return ts.tv_sec*1000.0+ts.tv_nsec/1.0e6;}
static int cmpd(const void*a,const void*b){double x=*(const double*)a,y=*(const double*)b;
    return (x>y)-(x<y);}
static double pct(double*s,int n,double p){if(n<=0)return 0.0;if(n==1)return s[0];
    double idx=(p/100.0)*(n-1);int lo=(int)idx,hi=lo+1<n?lo+1:n-1;double fr=idx-lo;
    return s[lo]*(1.0-fr)+s[hi]*fr;}

int main(int argc,char**argv){
  if(argc<6){fprintf(stderr,"usage: %s <host> <port> <group> <iters> <warmup> [csv] [timeout_ms]\n",argv[0]);return 2;}
  const char*host=argv[1];int port=atoi(argv[2]);const char*group=argv[3];
  int iters=atoi(argv[4]),warmup=atoi(argv[5]);const char*csv=(argc>6)?argv[6]:NULL;
  int TMO=(argc>7)?atoi(argv[7]):5000;

  SSL_CTX*ctx=SSL_CTX_new(TLS_client_method());
  if(!ctx){ERR_print_errors_fp(stderr);return 1;}
  SSL_CTX_set_min_proto_version(ctx,TLS1_3_VERSION);
  SSL_CTX_set_max_proto_version(ctx,TLS1_3_VERSION);
  SSL_CTX_set_verify(ctx,SSL_VERIFY_NONE,NULL);
  SSL_CTX_set_session_cache_mode(ctx,SSL_SESS_CACHE_OFF);
  SSL_CTX_set_options(ctx,SSL_OP_NO_TICKET);
  if(SSL_CTX_set1_groups_list(ctx,group)!=1){
    fprintf(stderr,"group '%s' not supported\n",group);
    ERR_print_errors_fp(stderr);SSL_CTX_free(ctx);return 1;}

  struct sockaddr_in addr;memset(&addr,0,sizeof addr);
  addr.sin_family=AF_INET;addr.sin_port=htons(port);
  if(inet_pton(AF_INET,host,&addr.sin_addr)!=1){
    fprintf(stderr,"bad addr %s\n",host);SSL_CTX_free(ctx);return 1;}

  int total=warmup+iters;
  double*all=calloc(iters,sizeof(double));
  FILE*fp=NULL;
  if(csv){fp=fopen(csv,"w");if(!fp){perror("fopen");return 1;}
    fprintf(fp,"group,iter,tcp_ms,tls_ms,total_ms,status,negotiated_group\n");}

  int ok=0,fail=0,tmo=0;const char*neg="?";
  for(int i=0;i<total;i++){
    int w=(i<warmup);double t0=now_ms();
    int fd=socket(AF_INET,SOCK_STREAM,0);
    if(fd<0){fail++;continue;}
    int one=1;setsockopt(fd,IPPROTO_TCP,TCP_NODELAY,&one,sizeof one);
    int fl=fcntl(fd,F_GETFL,0);fcntl(fd,F_SETFL,fl|O_NONBLOCK);

    int cr=connect(fd,(struct sockaddr*)&addr,sizeof addr);
    if(cr!=0&&errno!=EINPROGRESS){
      close(fd);fail++;
      if(fp&&!w)fprintf(fp,"%s,%d,,,,tcp_fail,\n",group,i-warmup);
      continue;}
    if(cr!=0){
      struct pollfd pfd={fd,POLLOUT,0};
      int pr=poll(&pfd,1,TMO);
      int soe=0;socklen_t sl=sizeof soe;
      if(pr<=0||getsockopt(fd,SOL_SOCKET,SO_ERROR,&soe,&sl)!=0||soe!=0){
        close(fd);fail++;if(pr==0)tmo++;
        if(fp&&!w)fprintf(fp,"%s,%d,,,,%s,\n",group,i-warmup,pr==0?"tcp_timeout":"tcp_fail");
        continue;}}
    double t1=now_ms();

    SSL*ssl=SSL_new(ctx);SSL_set_fd(ssl,fd);
    SSL_set_tlsext_host_name(ssl,"localhost");

    int r;double dl=t1+TMO;
    for(;;){
      r=SSL_connect(ssl);
      if(r==1)break;
      int e=SSL_get_error(ssl,r);
      if(e!=SSL_ERROR_WANT_READ&&e!=SSL_ERROR_WANT_WRITE){r=-1;break;}
      double rem=dl-now_ms();
      if(rem<=0){r=-2;break;}
      struct pollfd pfd={fd,(short)(e==SSL_ERROR_WANT_READ?POLLIN:POLLOUT),0};
      if(poll(&pfd,1,(int)rem)<=0){r=-2;break;}
    }
    double t2=now_ms();

    if(r==1){
      const char*n=SSL_group_to_name(ssl,SSL_get_negotiated_group(ssl));
      if(n)neg=n;
      if(!w){int k=i-warmup;all[k]=t2-t0;
        if(fp)fprintf(fp,"%s,%d,%.4f,%.4f,%.4f,ok,%s\n",group,k,t1-t0,t2-t1,t2-t0,n?n:"?");}
      ok++;
    }else{
      fail++;if(r==-2)tmo++;
      if(fp&&!w)fprintf(fp,"%s,%d,%.4f,%.4f,,%s,\n",group,i-warmup,t1-t0,t2-t1,
                        r==-2?"tls_timeout":"tls_fail");}
    SSL_free(ssl);close(fd);
  }
  if(fp)fclose(fp);

  int n=0;for(int i=0;i<iters;i++)if(all[i]>0.0)n++;
  double*s=calloc(n>0?n:1,sizeof(double));int j=0;double sum=0;
  for(int i=0;i<iters;i++)if(all[i]>0.0){s[j++]=all[i];sum+=all[i];}
  qsort(s,n,sizeof(double),cmpd);
  double mean=n?sum/n:0,var=0;
  for(int i=0;i<n;i++)var+=(s[i]-mean)*(s[i]-mean);
  double sd=n>1?sqrt(var/(n-1)):0;
  printf("group=%-18s negotiated=%-18s n=%d  fail=%d  tmo=%d  failrate=%.2f%%\n",
         group,neg,n,fail,tmo,(ok+fail)?100.0*fail/(ok+fail):0.0);
  if(n)printf("  HCT(ms)  mean=%.3f  sd=%.3f  p50=%.3f  p95=%.3f  p99=%.3f  min=%.3f  max=%.3f\n",
         mean,sd,pct(s,n,50),pct(s,n,95),pct(s,n,99),s[0],s[n-1]);
  free(s);free(all);SSL_CTX_free(ctx);return 0;
}
