
import pystan as ps
import pandas as pd
import arviz as az
import numpy as np
import pathlib
from math import ceil
from matplotlib.lines import Line2D
import matplotlib.pyplot as plt
import xarray
import bokeh.io
bokeh.io.output_notebook()
xarray.set_options(display_style="html")
import multiprocessing
multiprocessing.set_start_method("fork")

import warnings
warnings.simplefilter('ignore', FutureWarning)


class BayesRegression:
    """
    Implementation of Difference-in-Difference Design with a 
    Two-Way-Fixed-Effects Estimator where Markov-Chain-Monte-Carlo
    sampling methods (MCMC) are used in order to generate estimates
    of the causal effect of interest
    
    Parameters
    ----------
    intervention : datetime, default=dt.datetime(2017,5,10)
        This parameter desices which date will be used for splitting the units
        into pre-intervention Group and post-intervention group.
    var : String, default='ÖVP'
        Determines the dependent variable of the model. Alternatively 'SPÖ',
        'FPÖ' or 'Grüne' can be stated.
    impute : bool, default=True
    
    Attributes
    ----------
    model : StanModel 
        It is a stanModel yes
    """

    def __init__(self, var="ÖVP"):
        self.var = var
        self.model = ps.StanModel(file="model/model.stan", extra_compile_args=["-w"])
        self.post = None
    

    def sample(self, input_df, num_iter=12000, num_chains=4, num_thin=3, num_warmup=900):
        df = input_df.copy()
        y = df.loc[:, self.var].values
        # Intercept and unit FE
        df.loc[:, 'Intercept'] = 1
        keep = ['Intercept', 'Treatment', 'bins']
        df = df[keep]
        # Time FE
        for i in df.bins.unique():
            df[f'Group_{i}'] = np.where(df.bins==i,1,0)
        X = df.drop(columns=['Group_1', 'bins']).values         

        # Group Assignments for each Point
        D = pd.DataFrame()
        for i in df.bins.unique():
            D[f'Treatment_{i}'] = np.where((df.bins==i) & (df.Treatment==1),1,0)
        D = D.drop(columns=['Treatment_1']).values        
             
        data_dict = {"x": X, 
                "d": D,
                "y_obs": y, 
                "N": len(df), 
                "T": D.shape[1], 
                "K": X.shape[1]
        }
      
        fit = self.model.sampling(data=data_dict, 
                                iter=num_iter, 
                                chains=num_chains, 
                                warmup=num_warmup, 
                                thin=num_thin,
                                control=dict(adapt_delta=0.98),
                                seed=352553,
                                init='random'
        )

        self.post = az.from_pystan(posterior=fit, 
                                       posterior_predictive=["y_hat"], 
                                       observed_data=["y_obs"]
        )
            
            
    def _getSummary(self, beta, interval):
        coords = {"beta_dim_0":[beta]}
        tau = np.concatenate(self.post.posterior["beta"].sel(coords).values).flatten()
        
        mu = tau.mean()
        sd = tau.std()
        
        tau.sort()
        N = len(tau)
        
        # Conpute Probability
        if self.var == "SPÖ":
            prob = len([x for x in tau if x > 0]) / N
        else:
            prob = len([x for x in tau if x < 0]) / N
            
        # Compute Highest Density Intervals        
        nSampleCred = int(ceil(N * interval))
        # number of intervals to be compared
        nCI = N - nSampleCred
        # width of every proposed interval
        width = np.array([tau[i+nSampleCred] - tau[i] for i in range(nCI)])
        # index of lower bound of shortest interval (which is the HDI) 
        best  = width.argmin()
        # put it in a dictionary
        lower, upper = tau[best], tau[best + nSampleCred]

        return mu, sd, lower, upper, prob
        

    def summary(self, latex=False, interval=.89):
        df = pd.DataFrame(columns=['Mean', 'SD','lowHID', 'uppHDI', "P"])
        df.loc['Beta 0'] = self._getSummary(beta=0, interval=interval)
        for i in range(1,8):
            df.loc[len(df.index)] = self._getSummary(beta=i, interval=interval)
            
        if latex:
            print(df.round(3).to_latex(caption="Diff-in-Diff Linear Regression Output",
                    label="Diff_in_Diff", position="h"))
        else:
            return df
         

    def short_term(self, interval=.89, save=False):
        mu, _, lower, upper, prob = self._getSummary(beta=0, interval=interval)
        bounds = ([lower, upper] - mu).reshape(2,1)
        
        _,ax = plt.subplots(figsize=(12,4), facecolor='White', constrained_layout=True)
        tau = np.concatenate(self.post.posterior["beta"].sel({"beta_dim_0":[0]}).values).flatten()
        az.plot_kde(tau,
                    ax=ax, 
                    adaptive=True,
                    plot_kwargs={"linewidth": 1.5, "color": "black"},
                    rug_kwargs={"color": "black"},     
                    label=r'Posterior of $\hat{\tau}$'             
        )
        ax.vlines(0,
                    ymin=0,
                    ymax=.5,
                    alpha=.8,
                    colors='k',
                    ls='--',
                    lw=1
        )  
        ax.errorbar(x=np.mean(tau),
                    y=0.01,
                    xerr=abs(bounds),
                    elinewidth=1.5,
                    fmt='ok',
                    capsize=.1,
                    markerfacecolor="white",
                    label="Mean and 89% HDI",
        )
        ax.set_frame_on(False)
        ax.get_xaxis().tick_bottom()
        ax.axes.get_yaxis().set_visible(False) 
        xmin, xmax = ax.get_xaxis().get_view_interval()
        ymin, ymax = ax.get_yaxis().get_view_interval()
        ax.add_artist(Line2D((xmin, xmax), (ymin, ymin), color='black', linewidth=2))         
        if self.var == 'SPÖ':
            ax.text(0.3, .1, r'P($\hat{\tau} > 0$) =' +  f'{np.round(prob,4)}', fontsize=15)
            ax.legend(fancybox=True, loc='upper left')
        else:
            ax.text(-1.5, .1, r'P($\hat{\tau} < 0$) =' +  f'{np.round(prob,3)}', fontsize=15)
            ax.legend(fancybox=True, loc='upper right')
        if save == True:
            path = pathlib.Path(__file__).parent.parent / 'images' / f'short_term_{self.var}.pdf'
            plt.savefig(path, dpi=800, format='pdf')
        else:
            plt.show()
                        
                        
    def long_term(self, interval=.89, save=False):
        df = self.summary(interval=interval)
        # Add Intercept Group 
        df.reset_index(inplace=True, drop=True)
        df.loc[-1] = 0
        df.index = df.index + 1  
        df.sort_index(inplace=True) 
        # Compute Bounds for error Bars
        bounds = df.iloc[:,2:4].to_numpy()
        bounds[:, 0] -= df.iloc[:, 0].to_numpy()
        bounds[:, 1] -= df.iloc[:, 0].to_numpy()
        
        _,ax = plt.subplots(figsize=(12,5), facecolor='white', constrained_layout=True)
        ax.set_xlim([-.5, len(df.index)-.5])
        ax.set_ylim([-4.5, 4.5])
        ax.errorbar(x=df.index,
                    y=df.iloc[:,0].values,
                    yerr=abs(bounds.T),
                    elinewidth=1.2,
                    fmt='ok',
                    capsize=.1,
                    markerfacecolor="white",
        )
        ax.hlines(0, 
                    xmin=-.5,
                    xmax=len(df.index)-.5,
                    colors='black', 
                    linestyles='--',
                    linewidth=.8
        )
        label = []
        for i in range(len(df.index)):
            label.append(f'{i}')
        ax.set_xticks(df.index)
        ax.set_xlabel('Time Period', fontsize=22)
        ax.set_xticklabels(label)
        ax.set_ylabel('Coefficient', fontsize=22)
        if save == True:
            path = pathlib.Path(__file__).parent.parent / 'images' / f'long_term_{self.var}.pdf'
            plt.savefig(path, dpi=800, format='pdf')
        else:
            plt.show()


    def evaluate(self, save=False):
        with plt.style.context('seaborn-whitegrid'):
            fig = plt.figure(figsize=(14, 4), constrained_layout=True)
            spec = fig.add_gridspec(2, 3)
            ax0 = fig.add_subplot(spec[:, 2])
            az.plot_energy(self.post, 
                           ax=ax0, 
                           fill_alpha=[1,.7],
                           fill_color=('C7','k')
            )
            
            ax10 = fig.add_subplot(spec[0, 0])
            ax11 = fig.add_subplot(spec[0, 1])
            ax20 = fig.add_subplot(spec[1, 0])
            ax21 = fig.add_subplot(spec[1, 1])
            ax=np.array([[ax10,ax11], [ax20, ax21]])
            az.plot_trace(self.post,
                          var_names=['gamma', 'sigma'],
                          axes=ax,
                          compact=True,
                          combined=False,
                          chain_prop={"color":'k1'},
            )
            ax10.set_title(r"Posterior Distribution of Fixed Effects $\gamma$ and $\lambda$", fontsize=11)
            ax11.set_title(r"Trace of Fixed Effects $\gamma$ and $\lambda$", fontsize=11)
            ax20.set_title(r"Posterior Distribution of Variance $\sigma$", fontsize=11)
            ax21.set_title(r"Trace of Variance $\sigma$", fontsize=11)
            if save == True:
                path = pathlib.Path(__file__).parent.parent / 'images' / f'eval{self.var}.pdf'
                plt.savefig(path, dpi=200, format='pdf')
            else:
                plt.show()            
    
    
    def trace(self, param='beta', save=False):
        df = self.post
        df.rename({"beta": r"$\hat{\tau}$"}, inplace=True)
        if param=='beta':
            param=r"$\hat{\tau}$"
        with plt.style.context('arviz-whitegrid'):
            az.plot_trace(df,
                          var_names=[param],
                          compact=False,
                          combined=False,
                          chain_prop={"color":'k1'}
            )
        if save == True:
            path = pathlib.Path(__file__).parent.parent / 'images' / f'trace{self.var}.pdf'
            plt.savefig(path, dpi=200, format='pdf')
        else:
            plt.show()
    

    def trends(self, input_df, interval=0.89, save=False):
        true_post = None
        if self.post:
            true_post = self.post
        ra = input_df[~input_df.Institute.str.contains('Unique Research')]
        ur = input_df[~input_df.Institute.str.contains('Research Affairs')]
        ur['Treatment'] = np.where(ur.Institute.str.contains('Unique Research'),1,0).copy()
        
        ra = self.sample(ra)
        ra = self.summary(interval=interval)
        ur = self.sample(ur)   
        ur = self.summary(interval=interval)
        
        if true_post:
            self.post = true_post

        fig ,ax = plt.subplots(1,2, figsize=(24,5), sharex=True, sharey=True, constrained_layout=True, facecolor='white')
        for axs, model in enumerate([ra, ur]):
            df = model
            df.reset_index(inplace=True, drop=True)
            df.loc[-1] = 0 
            df.index = df.index + 1  # shifting index
            df.sort_index(inplace=True) 
            bounds = df.iloc[:,2:4].to_numpy()
            bounds[:, 0] -= df.iloc[:, 0].to_numpy()
            bounds[:, 1] -= df.iloc[:, 0].to_numpy()
            
            ax[axs].set_xlim([-.5, len(df.index)-.5])
            ax[axs].set_ylim([-4, 4])
            ax[axs].errorbar(x=df.index,
                            y=df.iloc[:,0].values,
                            yerr=abs(bounds.T),
                            elinewidth=1.2,
                            fmt='ok',
                            capsize=.1,
                            markerfacecolor="white",
            )
            ax[axs].hlines(0, 
                    xmin=-.5,
                    xmax=len(df.index)-.5,
                    colors='black', 
                    linestyles='--',
                    linewidth=.8
            )
            ax[axs].set_xticks(df.index)
            label = []
            for i in range(len(df.index)):
                label.append(f'{i}')
            ax[axs].set_xticklabels(label)
        ax[0].set_title('Research Affairs',fontsize=22)
        ax[1].set_title('Unique Research',fontsize=22)    
        fig.supylabel('Coefficient', fontsize=22)
        fig.supxlabel('Time Period', fontsize=22)
        if save == True:
            path = pathlib.Path(__file__).parent.parent / 'images' / f'trends{self.var}.pdf'
            plt.savefig(path, dpi=200, format='pdf')
        else:
            plt.show()


    def compareSim(self, tau):
        df = tau.T
        data = self.post
        data.rename({"beta": r"$\hat{\tau}$"}, inplace=True)
        param=r"$\hat{\tau}$"
        with plt.style.context('arviz-darkgrid'):
            az.plot_posterior(data,
                              var_names=[param],
                              ref_val=list(df.loc[1: ,self.var].values),
                              color='k',
                              ref_val_color='k',
                              )
            path = pathlib.Path(__file__).parent.parent / 'images' / 'sim.pdf'
            plt.savefig(path, dpi=200, format='pdf')


    def post_predictive(self):
        with az.style.context('arviz-whitegrid'):
            _ ,ax = plt.subplots(figsize=(12,6), constrained_layout=True)
            az.plot_ppc(self.post, data_pairs={"y_obs": "y_hat"},
                        alpha=.3,
                        num_pp_samples=1000,
                        ax=ax, 
                        legend=False
            )
            ax.set_title(f'Posterior Predictive plot of {self.var} against observed outcomes', fontsize=18)
            ax.legend(fancybox=True)
            plt.show()
            
            
if __name__ == "__main__":
    pass