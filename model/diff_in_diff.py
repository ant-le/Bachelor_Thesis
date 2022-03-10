
from cgi import test
import logging
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from datetime import datetime
from scipy import stats

class TwoWayFixedEffects:
    """
    Implementation of canonical Difference-in-Difference Design with a 
    Two-Way-Fixed-Effects Estimator where Ordinary Least Squares (OLS) 
    is used to fit a linear regression model to the data. The coefficients 
    beta = (beta_0, ..., beta_p) minimise the residual sum of squares between 
    the observed targets in the dataset and the targets predicted by the 
    linear approximation. The standard errors of the FE linear approximation only 
    hold for the 2*2 case of a canonical design.
    
    Parameters
    ----------
    intervention : datetime, default=dt.datetime(2017,5,10)
        This parameter desices which date will be used for splitting the units
        into pre-intervention Group and post-intervention group.
    var : String, default='ÖVP'
        Determines the dependent variable of the model. Alternatively 'SPÖ',
        'FPÖ' or 'Grüne' can be stated.
    test: String, default='t'
        Determines based on which distribution the standard errors will be 
        computed. For using the Standard Normal Distribution input 'z' to
        account for population data without (sampling) estimation error.
        
    Attributes
    ----------
    fit : df of shape (n_features, n_summaryStatistics)
        pd.DataFrame containing all relevant summary statistics. Depending on furhter
        specification hypothesis testing might be included or not.
    """

    def __init__(self, var='ÖVP', test='z'):
        self.var = var
        self.test = test
    

    def fit(self, input_df):
        """
        Linear approximation of the Two-Way Fixed Effects (causal) effect with 
        beta = (beta_0, ..., beta_p) being the parameters minimising the residual
        sum of squares based on an input pd.DataFrame and the relevant information
        stated in the constructor.
        
        Parameters
        ----------
        df : df of shape (n_units, n_features)
            Input DataFrame containing (at least) all relevant varialbes necessary for
            analysis.
        var_names list of length 2, default=["Date", "Institute"]
            Names of varaibles used for the fixed effects linear regression model. The
            interaction term is calculated manually.
        """
        df = input_df.copy()
        df = df[df['Date'] < datetime(2017,10,15)]
        df["Intercept"] = np.hstack([np.ones(len(df))])
        keep = ["Intercept", "Treatment", "Intervention", "DiD"]
        X = df[keep].values
        y = df.loc[:, self.var].values
        
        self.fit = self._getCoeffs(X,y)
        logging.info("OLS Regression successful!")
        
        
    def _getCoeffs(self, X, y):    
        # Computing the Estimates 
        invs_gram = np.linalg.inv(X.T @ X)
        df = X.shape[0]
        if self.test == 't':
            df -= X.shape[1] 

        # Get Coefficients
        betas = invs_gram @ (X.T @ y)
            
        # Compute Standard Errors
        yhat = X @ betas
        error = np.subtract(y, yhat)
        mse = np.divide(error.T @ error, df)
        se = np.sqrt(mse * invs_gram.diagonal())
                        
        # Construct Confidence Intervals
        CI = 1.96
        if self.test == 't':
            CI = stats.t.ppf(0.975 ,df)
        lower = betas - CI * se
        upper = betas + CI * se 
        
        # Hypothesis Testing
        score = np.divide(betas,se)
        p = 2*stats.norm.sf(abs(score))
        if test == 't':
            p = 2*(1-stats.t.cdf(score, df))
            
        df = pd.DataFrame(list(zip(betas, se, score, p, lower, upper)), 
                                            columns=['Coef', 'SE', f'{self.test}', 'p-value', '2.5% CI', '97.5% CI'], 
                                            index=["Intercept", "Institute", "Time Intervention", "Diff-in-Diff"])
                
        return df


    def summary(self, latex=False, plot=False):
        """
        Summary Statistics of the linear (tow-way FE) regression model. 
        
        Parameters
        ----------
        latex : bool, default=False
            Whether summary statistics should be returned as table or as tabular embedded
            in latex code.
        plot bool, default=False
            Whether result of Diff-in-Diff design should be illustrated graphically. Possibly 
            standard errors will also be used for the illustration of uncertainty levels.
        """
        df = self.fit.copy()
        
        if latex:
            print(df.drop(columns=[f'{self.test}', 'p-value']).round(decimals=3).to_latex(caption="Output of Two-Way Fixed Effects OLS Linear Regression Model",
                                label="TWFE_Output", position="h!"))
        else:       
            print(df.round(decimals=3))
            if plot:
                values = df.loc[:, "Coef"]              
                with plt.style.context('ggplot'):
                    fig, ax = plt.subplots(figsize=(10,5))
                    ax.plot(["Jan 1 - May 10", "May 11 - October 9"], 
                            [values[:2].sum(), values.sum()], 
                            label="Research Affairs", lw=2, c="gray")
                    ax.plot(["Jan 1 - May 10", "May 11 - October 9"], 
                                [values[0], values[[0,2]].sum()], 
                            label="Other Institutes", lw=2, c="black")
                    ax.plot(["Jan 1 - May 10", "May 11 - October 9"], 
                            [values[:2].sum(), values[:3].sum()], 
                            label="Counterfactual", lw=2, color="darkgrey", ls="-.")
                    ax.set_ylabel("Percentage Points of " + str(self.var))
                    ax.legend(fancybox=True)
                    ax.set_title("Plot of Counterfacutals of Naive Diff-in-Diff Estimator")
                    plt.show()

  
if __name__ == "__main__":
    data = pd.read_csv("/Users/anton/Documents/University/Semester_7/Bachelor_Thesis/data/analysis/polls.csv")
    data.rename(columns={'datum':'Date'}, inplace=True)
    data["Date"] = pd.to_datetime(data.Date)
    model = TwoWayFixedEffects(var='SPÖ')
    model.fit(data)
    model.summary(plot=True)